"""Read-only access to hermes-dev-team runs: projects, run list, progress logs, live workers. Stdlib only.

Reads each project's <scratch>/runs.log, <scratch>/runs/*.progress.log and <scratch>/runs/*.lock (see README
"File format"). Writes nothing in any project; the only file it writes is its own config.json.
"""
import datetime, json, os, pathlib, re, sys, threading, time

CONFIG = pathlib.Path(os.environ.get("APPDATA") if sys.platform == "win32" and os.environ.get("APPDATA")
                      else os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "hermes-dev-watch" / "config.json"

# <stamp>-<role>, the progress log's stem. Roles may have digits and `-` (e.g. a future `fix-dev`); no `/` or `.`,
# so an id can never leave runs/.
RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z][a-z0-9-]*$")
# Newest run-file format this watcher reads (the kit's teamcfg.RUN_FORMAT, written as fmt= / "fmt"; see the kit's
# docs/watch-contract.md). A line or lock without fmt is format 1 (kit 0.13.2 and older).
KNOWN_FORMAT = 1
MAX_RUNS = 200                                         # newest runs listed per project
CHUNK = 256 * 1024                                     # most progress bytes sent per poll
TAIL_LINES = 14                                        # lines shown on a live tile
RESCAN_S = 15
SKIP_DIRS = {"node_modules", ".git", "vendor", "dist", "build", ".venv", "venv", "__pycache__", "target"}


class Projects:
    """{id: scratch path}; ids are folder names, made unique with the parent folder when two clash."""

    def __init__(self, fixed, roots):
        self.fixed, self.roots, self.map, self.at, self.lock = fixed, roots, {}, 0.0, threading.Lock()
        self.extra = []                                # session-only scratch folders (flags, cwd)

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

    def set(self, fixed, roots):
        with self.lock:
            self.fixed, self.roots, self.at = fixed, roots, 0.0

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
                                 "repo": kv.get("repo"), "denials": kv.get("denials"), "backend": kv.get("backend"),
                                 "fmt": fmt_of(kv.get("fmt"))}
    return out


def fmt_of(v):
    """The run-file format of a runs.log line or lock: an int, 1 when absent, 0 when unreadable."""
    if v is None:
        return 1
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


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


GROUPS = ("running", "pass", "fail", "none")
DAYS = {"today": 1, "7": 7, "30": 30}
ROLE_NAME = re.compile(r"^[a-z0-9-]+$")


def verdict_group(r):
    v = r.get("verdict") or ""
    if r.get("live"):
        return "running"
    return "pass" if v.startswith("PASS") else "fail" if v.startswith(("FAIL", "ERROR")) else "none"


def filter_runs(runs, flt, now):
    """The runs matching the run filter, same order. flt comes from the page: bad input is ignored, never raises."""
    flt = flt if isinstance(flt, dict) else {}
    v, ro, days, q = flt.get("verdict"), flt.get("role"), flt.get("days"), flt.get("q")
    v = {x for x in v if x in GROUPS} if isinstance(v, list) else set()
    ro = {x for x in ro if isinstance(x, str) and ROLE_NAME.match(x)} if isinstance(ro, list) else set()
    q = q[:200].lower() if isinstance(q, str) else ""
    first = None
    if isinstance(days, str) and days in DAYS:
        first = (now.date() - datetime.timedelta(days=DAYS[days] - 1)).strftime("%Y%m%d")
    out = []
    for r in runs:
        if v and verdict_group(r) not in v:
            continue
        if ro and r.get("role") not in ro:
            continue
        if first and str(r.get("stamp") or "")[:8] < first:
            continue
        if q and q not in " ".join(str(r.get(k) or "") for k in
                                   ("role", "ticket", "feature", "verdict", "project", "model")).lower():
            continue
        out.append(r)
    return out


def project_state(pid, scratch, flt=None, now=None, open_run=None):
    now = now or datetime.datetime.now()
    runs_dir = scratch / "runs"
    logged = runs_log(scratch)
    live = {f"{d.get('stamp')}-{d.get('role')}": d for d in live_locks(scratch)}
    ids = {p.name[:-len(".progress.log")] for p in runs_dir.glob("*.progress.log")} if runs_dir.is_dir() else set()
    ids |= set(logged) | set(live)
    runs = []
    for rid in sorted((i for i in ids if RUN_ID.match(i)), reverse=True):
        r = {"id": rid, "project": pid, "stamp": rid[:15], "role": rid[16:], **logged.get(rid, {})}
        if rid in live:
            lk = live[rid]
            r.update(live=True, ticket=lk.get("ticket"), feature=lk.get("feature"), repo=lk.get("repo"),
                     tail=tail(runs_dir / f"{rid}.progress.log", TAIL_LINES))
        elif "verdict" not in r:
            r["verdict"] = "NO RESULT stopped or crashed"
        runs.append(r)
    seen = max([r.get("fmt", 1) for r in logged.values()] + [fmt_of(d.get("fmt")) for d in live.values()] + [1])
    matched = filter_runs(runs, flt, now)
    today = now.strftime("%Y%m%d")
    done = [r for r in runs if not r.get("live") and r["stamp"][:8] == today]
    opened = next((r for r in runs if r["id"] == open_run), None) if isinstance(open_run, str) else None
    return {"id": pid, "path": scratch.as_posix(), "open": opened, "runs": matched[:MAX_RUNS], "total": len(matched), "run_count": len(runs),
            "live_runs": [r for r in runs if r.get("live")], "roles": sorted({r["role"] for r in runs}),
            "today": {"runs": len(done), "pass": sum(verdict_group(r) == "pass" for r in done),
                      "cost": sum(r["cost"] for r in done if r.get("cost") is not None)},
            "live": len(live), "fmt": seen, "newer_format": seen > KNOWN_FORMAT}


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
    text = data[:cut].decode("utf-8", "replace").replace("\r\n", "\n")   # Windows logs: \r\n -> \n
    return {"text": text, "offset": offset + cut, "size": size}


def load_config(path=CONFIG):
    """{"roots": [...], "scratch": [...]} from config.json; missing file = empty lists."""
    p = pathlib.Path(path)
    try:
        d = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    except ValueError:
        d = {}
    return {"roots": [str(x) for x in d.get("roots") or []], "scratch": [str(x) for x in d.get("scratch") or []]}


def save_config(cfg, path=CONFIG):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"roots": cfg["roots"], "scratch": cfg["scratch"]}, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def resolve(paths):
    return [pathlib.Path(x).expanduser().resolve() for x in paths]
