#!/usr/bin/env python3
"""hermes-dev-watch: live, read-only view of hermes-dev-team worker runs across projects, as a small local web page.
No model is called. Stdlib only; needs nothing from the kit (it reads the kit's files, see README "File format").

Reads each project's <scratch>/runs.log, <scratch>/runs/*.progress.log and the worker lock(s) (<scratch>/runs/*.lock);
writes nothing, and has no stop button (use `scratch.py stop`). The page polls about once a second: every running
worker, in every project, shows its newest lines as they are written.

Projects: ./.scratch or ../.scratch of the current folder, every --scratch PATH, and every `.scratch` folder with a
runs.log or runs/ found up to 3 levels below each --root DIR. Roots and scratch folders can also come from
~/.config/hermes-dev-watch/config.json ({"roots": [...], "scratch": [...], "port": 8765}); flags add to it.
Roots are rescanned every 15 s, so a new project appears without a restart.

Usage:
    python watch.py [--port 8765] [--scratch PATH ...] [--root DIR ...] [--config FILE]
    e.g. python watch.py --root ~/Dokumen/projects --root ~/Proyek
then open http://127.0.0.1:8765 (Hermes desktop: in the preview pane, next to the chat). Binds 127.0.0.1 only.
"""
import argparse, json, os, pathlib, re, sys, threading, time, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CONFIG = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "hermes-dev-watch" / "config.json"

RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z]+$")          # <stamp>-<role>, the progress log's stem
MAX_RUNS = 200                                         # newest runs listed per project
CHUNK = 256 * 1024                                     # most progress bytes sent per poll
TAIL_LINES = 14                                        # lines shown on a live tile
RESCAN_S = 15
SKIP_DIRS = {"node_modules", ".git", "vendor", "dist", "build", ".venv", "venv", "__pycache__", "target"}


class Projects:
    """{id: scratch path}; ids are folder names, made unique with the parent folder when two clash."""

    def __init__(self, fixed, roots):
        self.fixed, self.roots, self.map, self.at, self.lock = fixed, roots, {}, 0.0, threading.Lock()

    def _scan(self):
        found = list(self.fixed)
        for root in self.roots:
            base_depth = len(root.parts)
            for d, dirs, _ in os.walk(root):
                p = pathlib.Path(d)
                if p.name == ".scratch":
                    if (p / "runs.log").is_file() or (p / "runs").is_dir():
                        found.append(p.resolve())
                    dirs[:] = []
                    continue
                dirs[:] = [x for x in dirs if x not in SKIP_DIRS and (x == ".scratch" or not x.startswith("."))]
                if len(p.parts) - base_depth >= 3:
                    dirs[:] = [x for x in dirs if x == ".scratch"]
        out, seen = {}, set()
        for s in found:
            if s in seen or not s.is_dir():
                continue
            seen.add(s)
            name = s.parent.name if s.name == ".scratch" else s.name
            if name in out:
                name = f"{s.parent.parent.name}/{name}"
            out[name] = s
        return out

    def get(self):
        with self.lock:
            if time.time() - self.at > RESCAN_S:
                self.map, self.at = self._scan(), time.time()
            return dict(self.map)


def runs_log(scratch):
    """{run id: {...}} from runs.log (tab-separated: stamp, role, model, verdict, turns=, secs, key=value...)."""
    out, p = {}, scratch / "runs.log"
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        f = line.split("\t")
        if len(f) < 6:
            continue
        kv = dict(x.split("=", 1) for x in f[4:] if "=" in x)
        try:
            cost = float(kv["list$"]) if kv.get("list$") not in (None, "None") else None
        except ValueError:
            cost = None
        out[f"{f[0]}-{f[1]}"] = {"model": f[2], "verdict": f[3], "turns": kv.get("turns"), "secs": f[5].rstrip("s"),
                                 "cost": cost, "ticket": kv.get("ticket"), "feature": kv.get("feature"),
                                 "repo": kv.get("repo"), "denials": kv.get("denials"), "backend": kv.get("backend")}
    return out


def pid_alive(pid):
    """True when a process with this pid is running. Never signals it (os.kill(pid, 0) TERMINATES it on Windows).
    Same logic as the kit's teamcfg.pid_alive, copied so this repo stands alone."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)           # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259           # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def live_locks(scratch):
    """Running workers: every <scratch>/runs/*.lock whose launcher or worker pid is alive (today one worker.lock)."""
    out = []
    for p in sorted((scratch / "runs").glob("*.lock")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and (pid_alive(d.get("launcher_pid")) or pid_alive(d.get("worker_pid"))):
            out.append(d)
    return out


def tail(path, n):
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            data = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    lines = [x for x in data.splitlines() if x.strip()]
    return lines[-n:] if size <= 8192 else lines[1:][-n:]


def project_state(pid, scratch):
    runs_dir = scratch / "runs"
    logged = runs_log(scratch)
    live = {f"{d.get('stamp')}-{d.get('role')}": d for d in live_locks(scratch)}
    ids = {p.name[:-len(".progress.log")] for p in runs_dir.glob("*.progress.log")} if runs_dir.is_dir() else set()
    ids |= set(logged) | set(live)
    runs = []
    for rid in sorted((i for i in ids if RUN_ID.match(i)), reverse=True)[:MAX_RUNS]:
        r = {"id": rid, "project": pid, "stamp": rid[:15], "role": rid[16:], **logged.get(rid, {})}
        if rid in live:
            lk = live[rid]
            r.update(live=True, ticket=lk.get("ticket"), feature=lk.get("feature"), repo=lk.get("repo"),
                     tail=tail(runs_dir / f"{rid}.progress.log", TAIL_LINES))
        elif "verdict" not in r:
            r["verdict"] = "NO RESULT stopped or crashed"
        runs.append(r)
    return {"id": pid, "path": scratch.as_posix(), "runs": runs, "live": len(live)}


def progress(scratch, rid, offset):
    if not RUN_ID.match(rid or ""):
        return None
    p = scratch / "runs" / f"{rid}.progress.log"
    if not p.is_file():
        return {"text": "", "offset": 0, "size": 0}
    size = p.stat().st_size
    offset = 0 if offset > size else offset                # file was rewritten: start over
    with open(p, "rb") as f:
        f.seek(offset)
        data = f.read(CHUNK)
    cut = data.rfind(b"\n") + 1                            # only whole lines; the rest comes next poll
    return {"text": data[:cut].decode("utf-8", "replace"), "offset": offset + cut, "size": size}


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Workers</title>
<style>
:root{--bg:#0e0f12;--panel:#15171c;--panel2:#1b1e24;--line:#262a32;--fg:#e6e8ec;--mut:#8b919c;--dim:#5d636e;
 --acc:#7c9cff;--ok:#3ecf8e;--bad:#ff6b6b;--warn:#f5a524;--say:#b6a6ff;--edit:#5fb3ff;--r:10px;
 --dev:#5fb3ff;--reviewer:#c08bff;--docs:#3ecfc4;--researcher:#f5a524;--other:#8b919c}
@media (prefers-color-scheme:light){:root{--bg:#f6f7f9;--panel:#fff;--panel2:#f1f3f6;--line:#e3e6eb;--fg:#16181d;
 --mut:#5f6672;--dim:#9aa1ac;--acc:#3d63e0;--ok:#119a62;--bad:#d93c3c;--warn:#b7700a;--say:#6b55d6;--edit:#1f76c9}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 Inter,ui-sans-serif,system-ui,sans-serif;
 height:100vh;display:flex;flex-direction:column;overflow:hidden}
button,select,input{font:inherit;color:inherit}
header{display:flex;align-items:center;gap:10px;padding:10px 14px;border-bottom:1px solid var(--line);background:var(--panel);flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.2px;display:flex;align-items:center;gap:8px}
.brand i{width:9px;height:9px;border-radius:50%;background:var(--dim)}
.brand i.on{background:var(--ok);animation:ping 1.6s infinite}
@keyframes ping{0%{box-shadow:0 0 0 0 color-mix(in srgb,var(--ok) 60%,transparent)}100%{box-shadow:0 0 0 8px transparent}}
select,input{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:5px 9px;outline:none}
select:focus,input:focus{border-color:var(--acc)}
#q{width:190px}
.sp{flex:1}
.stat{color:var(--mut);font-size:12px;white-space:nowrap}.stat b{color:var(--fg);font-weight:600}
.btn{background:var(--panel2);border:1px solid var(--line);border-radius:8px;padding:4px 10px;cursor:pointer;white-space:nowrap}
.btn:hover{border-color:var(--acc)}.btn.on{background:color-mix(in srgb,var(--acc) 18%,transparent);border-color:var(--acc)}
.wrap{flex:1;display:flex;min-height:0}
aside{width:310px;flex:none;border-right:1px solid var(--line);overflow:auto;background:var(--panel)}
.day{position:sticky;top:0;background:var(--panel);padding:10px 14px 4px;color:var(--dim);font-size:11px;
 text-transform:uppercase;letter-spacing:.8px;z-index:1}
.run{margin:2px 8px;padding:8px 10px;border-radius:8px;cursor:pointer;border:1px solid transparent}
.run:hover{background:var(--panel2)}.run.sel{background:var(--panel2);border-color:var(--line)}
.row{display:flex;align-items:center;gap:6px;min-width:0}
.role{font-size:11px;font-weight:600;padding:1px 7px;border-radius:99px;background:color-mix(in srgb,var(--c) 16%,transparent);color:var(--c);flex:none}
.when{color:var(--dim);font-size:12px;margin-left:auto;white-space:nowrap}
.what{margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.proj{color:var(--mut);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.v{font-size:12px;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--mut)}
.v b{font-weight:600}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
main{flex:1;min-width:0;display:flex;flex-direction:column}
.empty{margin:auto;text-align:center;color:var(--mut);line-height:1.8}.empty h2{color:var(--fg);font-size:16px;margin:0 0 6px}
.board{flex:1;overflow:auto;padding:14px;display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));align-content:start}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:var(--r);overflow:hidden;cursor:pointer;display:flex;flex-direction:column}
.tile:hover{border-color:var(--acc)}
.th{padding:10px 12px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:8px;min-width:0}
.th .t{font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--ok);flex:none;animation:ping 1.6s infinite}
.tb{padding:6px 0;height:250px;overflow:hidden;display:flex;flex-direction:column;justify-content:flex-end;
 -webkit-mask-image:linear-gradient(to bottom,transparent,#000 40px);mask-image:linear-gradient(to bottom,transparent,#000 40px)}
.dh{padding:12px 16px;border-bottom:1px solid var(--line);background:var(--panel)}
.dh .t{display:flex;align-items:center;gap:8px;font-size:15px;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.chip{font-size:12px;color:var(--mut);background:var(--panel2);border:1px solid var(--line);border-radius:6px;padding:1px 7px}
.tools{display:flex;gap:6px;margin-top:10px;align-items:center;flex-wrap:wrap}
.log{flex:1;overflow:auto;padding:6px 0 30px;font:12px/1.55 "JetBrains Mono",ui-monospace,Menlo,monospace}
.l{display:flex;gap:10px;padding:1px 16px}
.log .l:hover{background:var(--panel2)}
.l .ts{color:var(--dim);width:46px;flex:none;text-align:right}
.l .k{width:64px;flex:none;font-size:11px;font-weight:600;color:var(--mut);padding-top:1px;overflow:hidden;text-overflow:ellipsis}
.l .x{white-space:pre-wrap;word-break:break-word;min-width:0}
.l.say .k,.l.say .x{color:var(--say)}.l.say .x{font-family:Inter,ui-sans-serif,system-ui,sans-serif;font-size:12.5px}
.l.edit .k{color:var(--edit)}.l.bash .k{color:var(--warn)}
.l.denied{background:color-mix(in srgb,var(--bad) 10%,transparent)}.l.denied .k,.l.denied .x{color:var(--bad)}
.l.error .k,.l.error .x{color:var(--warn)}
.tile .l{padding:1px 12px;font:11.5px/1.5 "JetBrains Mono",ui-monospace,Menlo,monospace}.tile .l .ts{width:40px}
.tile .l .x{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
::-webkit-scrollbar{width:10px;height:10px}::-webkit-scrollbar-thumb{background:var(--line);border-radius:10px;border:2px solid transparent;background-clip:padding-box}
</style></head><body>
<header>
 <div class="brand"><i id="beacon"></i>Workers</div>
 <select id="proj"></select>
 <input id="q" placeholder="Filter: role, ticket, verdict…">
 <span class="sp"></span>
 <span class="stat" id="stats"></span>
 <button class="btn" id="livebtn">Live</button>
</header>
<div class="wrap"><aside id="side"></aside><main id="main"></main></div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// view.k: 'live' = board of running workers; 'run' = one run's log. Opening a run is sticky until "Live" or "←".
let S={projects:[]},proj=localStorage.getItem('proj')||'*',view={k:'live'},off=0,logFor=null,filt='all',follow=true;
const ROLES=['dev','reviewer','docs','researcher'];
const rc=r=>`--c:var(--${ROLES.includes(r)?r:'other'})`;
const sdate=s=>new Date(+s.slice(0,4),+s.slice(4,6)-1,+s.slice(6,8),+s.slice(9,11),+s.slice(11,13),+s.slice(13,15));
const hm=d=>d.toTimeString().slice(0,5);
const ymd=d=>d.getFullYear()+String(d.getMonth()+1).padStart(2,'0')+String(d.getDate()).padStart(2,'0');
function dayLabel(d){const t=new Date();t.setHours(0,0,0,0);const x=new Date(d);x.setHours(0,0,0,0);
 const n=Math.round((t-x)/864e5);return n===0?'Today':n===1?'Yesterday':x.toLocaleDateString(undefined,{weekday:'short',day:'numeric',month:'short'})}
function dur(s){s=+s;if(!(s>=0))return'';return s<60?s+'s':s<3600?Math.floor(s/60)+'m '+(s%60)+'s':Math.floor(s/3600)+'h '+Math.floor(s%3600/60)+'m'}
function vk(v){v=v||'';return /^PASS/.test(v)?'ok':/^(FAIL|ERROR)/.test(v)?'bad':'warn'}
function vtxt(r){if(r.live)return'<b class="ok">running</b> · '+dur(Math.round((Date.now()-sdate(r.stamp))/1e3));
 const v=r.verdict||'',m=v.match(/^(\S+)\s*(.*)$/)||['',v,''];return `<b class="${vk(v)}">${esc(m[1])}</b> ${esc(m[2])}`}
function title(r){return r.ticket&&r.ticket!=='-'?r.ticket.replace(/\.md$/,''):(r.feature||'—')}
function kind(x){if(x.startsWith('say: '))return['say','says',x.slice(5)];if(x.startsWith('DENIED '))return['denied','DENIED',x.slice(7)];
 if(x.startsWith('exit!=0 '))return['error','failed',x.slice(8)];const sp=x.indexOf(' '),t=sp<0?x:x.slice(0,sp),rest=sp<0?'':x.slice(sp+1);
 const k=/^(Edit|Write|MultiEdit|NotebookEdit|write_file|patch)$/.test(t)?'edit':/^(Bash|terminal)$/.test(t)?'bash':'';return[k,t,rest]}
function lineHTML(l){const m=l.match(/^\s*\[\s*(\d+)s\]\s?(.*)$/);
 if(!m)return`<div class="l"><span class="ts"></span><span class="k"></span><span class="x">${esc(l)}</span></div>`;
 const [k,t,x]=kind(m[2]);return`<div class="l ${k}" data-k="${k||'other'}"><span class="ts">${dur(m[1])}</span><span class="k">${esc(t)}</span><span class="x" title="${esc(x)}">${esc(x)}</span></div>`}
function allRuns(){return S.projects.filter(p=>proj==='*'||p.id===proj).flatMap(p=>p.runs).sort((a,b)=>a.stamp<b.stamp?1:a.stamp>b.stamp?-1:0)}
function liveRuns(){return allRuns().filter(r=>r.live)}
function find(pid,id){const p=S.projects.find(x=>x.id===pid);return p&&p.runs.find(r=>r.id===id)}
function renderTop(){
 const opts=[['*','All projects',S.projects.reduce((a,p)=>a+p.live,0)],...S.projects.map(p=>[p.id,p.id,p.live])];
 if(!opts.some(o=>o[0]===proj))proj='*';
 const h=opts.map(([v,n,l])=>`<option value="${esc(v)}" ${v===proj?'selected':''}>${esc(n)}${l?` · ${l} running`:''}</option>`).join('');
 if($('proj').dataset.h!==h){$('proj').innerHTML=h;$('proj').dataset.h=h}
 const rs=allRuns(),today=ymd(new Date()),td=rs.filter(r=>r.stamp.startsWith(today)&&!r.live);
 const pass=td.filter(r=>vk(r.verdict)==='ok').length,cost=td.reduce((a,r)=>a+(r.cost||0),0),lv=liveRuns().length;
 $('stats').innerHTML=`today <b>${td.length}</b> runs · <b class="ok">${pass}</b> pass · <b class="bad">${td.length-pass}</b> fail · list <b>$${cost.toFixed(2)}</b>`;
 $('beacon').className=lv?'on':'';$('livebtn').textContent=`Live${lv?' · '+lv:''}`;$('livebtn').classList.toggle('on',view.k==='live');
}
function renderSide(){
 const q=$('q').value.trim().toLowerCase(),rs=allRuns().filter(r=>!q||[r.role,r.ticket,r.feature,r.verdict,r.project,r.model].join(' ').toLowerCase().includes(q));
 let h='',last='';
 for(const r of rs){const d=dayLabel(sdate(r.stamp));if(d!==last){h+=`<div class="day">${d}</div>`;last=d}
  const sel=view.k==='run'&&view.p===r.project&&view.id===r.id;
  h+=`<div class="run ${sel?'sel':''}" data-p="${esc(r.project)}" data-id="${r.id}"><div class="row">
   ${r.live?'<span class="pulse"></span>':''}<span class="role" style="${rc(r.role)}">${esc(r.role)}</span>
   ${proj==='*'?`<span class="proj">${esc(r.project)}</span>`:''}<span class="when">${hm(sdate(r.stamp))}${!r.live&&r.secs?' · '+dur(r.secs):''}</span></div>
   <div class="what" title="${esc(r.feature)}">${esc(title(r))}</div><div class="v">${vtxt(r)}</div></div>`}
 const sc=$('side').scrollTop;$('side').innerHTML=h||'<div class="empty" style="padding:30px">No runs</div>';$('side').scrollTop=sc;
 for(const d of document.querySelectorAll('.run'))d.onclick=()=>open(d.dataset.p,d.dataset.id);
}
function open(p,id){view={k:'run',p,id};logFor=null;render();pull()}
function renderBoard(){
 const lv=liveRuns();logFor=null;
 if(!lv.length){const r=allRuns()[0];
  $('main').innerHTML=`<div class="empty"><h2>No worker running</h2>${r?`Last run: <span class="role" style="${rc(r.role)}">${esc(r.role)}</span> ${esc(title(r))}<br>${vtxt(r)}<br><br><button class="btn" id="openlast">Open last run</button>`:'Start one from the planner.'}</div>`;
  if(r)$('openlast').onclick=()=>open(r.project,r.id);return}
 $('main').innerHTML=`<div class="board">${lv.map(r=>`<div class="tile" data-p="${esc(r.project)}" data-id="${r.id}">
  <div class="th"><span class="pulse"></span><span class="role" style="${rc(r.role)}">${esc(r.role)}</span>
  <span class="t">${esc(title(r))}</span><span class="when">${esc(r.project)} · ${dur(Math.round((Date.now()-sdate(r.stamp))/1e3))}</span></div>
  <div class="tb">${(r.tail||[]).map(lineHTML).join('')||'<div class="l"><span class="x" style="color:var(--dim)">starting…</span></div>'}</div></div>`).join('')}</div>`;
 for(const d of document.querySelectorAll('.tile'))d.onclick=()=>open(d.dataset.p,d.dataset.id);
}
function renderDetail(){
 const r=find(view.p,view.id);if(!r){view={k:'live'};return renderBoard()}
 const key=view.p+'/'+view.id;
 const chips=[r.project,r.repo&&r.repo!==r.project?r.repo:'',r.feature,r.ticket&&r.ticket!=='-'?r.ticket:'',r.model,r.backend&&r.backend!=='claude'?r.backend:'',
  r.turns&&r.turns!=='-'?r.turns+' turns':'',!r.live&&r.secs?dur(r.secs):'',r.cost!=null?'$'+r.cost.toFixed(2)+' list':'',r.denials&&r.denials!=='0'?r.denials+' denied':''].filter(Boolean);
 const head=`<div class="t"><button class="btn" id="back" title="Back to live">←</button>${r.live?'<span class="pulse"></span>':''}<span class="role" style="${rc(r.role)}">${esc(r.role)}</span>${esc(title(r))}</div>
  <div class="v" style="margin-top:6px;font-size:13px;white-space:normal">${vtxt(r)}</div>
  <div class="chips">${chips.map(c=>`<span class="chip">${esc(c)}</span>`).join('')}</div>
  <div class="tools">${['all','say','edit','bash','denied','error'].map(f=>`<button class="btn ${filt===f?'on':''}" data-f="${f}">${f}</button>`).join('')}
  <span class="sp"></span><label class="stat"><input type="checkbox" id="fol" ${follow?'checked':''}> follow</label></div>`;
 if(logFor!==key){$('main').innerHTML=`<div class="dh" id="dh"></div><div class="log" id="log"></div>`;logFor=key;off=0}
 $('dh').innerHTML=head;
 document.getElementById('fs').textContent=filt==='all'?'':`.log .l:not([data-k="${filt}"]){display:none}`;
 $('back').onclick=()=>{view={k:'live'};render()};
 $('fol').onchange=e=>follow=e.target.checked;
 for(const b of document.querySelectorAll('[data-f]'))b.onclick=()=>{filt=b.dataset.f;renderDetail()};
}
function render(){renderTop();renderSide();if(view.k==='run')renderDetail();else renderBoard()}
let pulling=false;
async function pull(){
 if(view.k!=='run'||pulling)return;const L=$('log');if(!L)return;pulling=true;const key=logFor;
 try{const p=await (await fetch(`/api/progress?p=${encodeURIComponent(view.p)}&run=${view.id}&offset=${off}`)).json();
  if(key!==logFor)return;
  if(p.text){const first=off===0;L.insertAdjacentHTML('beforeend',p.text.split('\n').filter(Boolean).map(lineHTML).join(''));
   if(follow||first)L.scrollTop=L.scrollHeight}
  if(p.offset!==undefined)off=p.offset;
  if(!L.children.length&&!p.text)L.innerHTML='<div class="empty" style="padding:30px">No progress log for this run<br><small>runs/ stays on the machine that ran it</small></div>';
 }finally{pulling=false}}
async function tick(){
 try{S=await (await fetch('/api/state')).json();render();await pull()}catch(e){$('stats').textContent='watch.py not reachable'}
 setTimeout(tick,1000)}
const st=document.createElement('style');st.id='fs';document.head.appendChild(st);
$('proj').onchange=e=>{proj=e.target.value;localStorage.setItem('proj',proj);if(view.k==='run'&&proj!=='*'&&view.p!==proj)view={k:'live'};render()};
$('q').oninput=renderSide;
$('livebtn').onclick=()=>{view={k:'live'};render()};
tick();
</script></body></html>"""


def make_handler(projects):
    class H(BaseHTTPRequestHandler):
        def send(self, code, body, ctype):
            b = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path == "/":
                return self.send(200, PAGE, "text/html; charset=utf-8")
            if u.path == "/api/state":
                ps = [project_state(pid, s) for pid, s in sorted(projects.get().items())]
                return self.send(200, json.dumps({"projects": ps}), "application/json")
            if u.path == "/api/progress":
                scratch = projects.get().get((q.get("p") or [""])[0])      # only a known project, never a path
                try:
                    off = max(0, int((q.get("offset") or ["0"])[0]))
                except ValueError:
                    off = 0
                d = progress(scratch, (q.get("run") or [""])[0], off) if scratch else None
                if d is None:
                    return self.send(400, '{"error": "bad project or run id"}', "application/json")
                return self.send(200, json.dumps(d), "application/json")
            self.send(404, "not found", "text/plain")

        def log_message(self, format, *args):     # quiet: one line per poll would flood the terminal
            pass
    return H


def main():
    ap = argparse.ArgumentParser(description="Live, read-only view of hermes-dev-team worker runs.")
    ap.add_argument("--port", type=int)
    ap.add_argument("--scratch", action="append", default=[], help="a scratch folder (repeatable)")
    ap.add_argument("--root", action="append", default=[], help="find .scratch folders up to 3 levels below (repeatable)")
    ap.add_argument("--config", default=str(CONFIG), help=f"JSON with roots/scratch/port (default {CONFIG})")
    a = ap.parse_args()
    cfg = {}
    cp = pathlib.Path(a.config).expanduser()
    if cp.is_file():
        try:
            cfg = json.loads(cp.read_text(encoding="utf-8"))
        except ValueError as e:
            print(f"WATCH STOP {cp} is not valid JSON: {e}"); return 1
    port = a.port or int(cfg.get("port") or 8765)
    fixed = [pathlib.Path(s).expanduser().resolve() for s in list(cfg.get("scratch") or []) + a.scratch]
    for here in (pathlib.Path.cwd() / ".scratch", pathlib.Path.cwd().parent / ".scratch"):   # a repo or workspace
        if here.is_dir():
            fixed.insert(0, here.resolve())
            break
    roots = [pathlib.Path(r).expanduser().resolve() for r in list(cfg.get("roots") or []) + a.root]
    projects = Projects(fixed, roots)
    found = projects.get()
    if not found:
        print(f"WATCH STOP no scratch folder found (run inside a project, pass --scratch / --root, or write {CONFIG})")
        return 1
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(projects))
    print(f"WATCH OK http://127.0.0.1:{port}  projects: {', '.join(sorted(found))}  (Ctrl+C stops)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
