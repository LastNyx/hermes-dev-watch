#!/usr/bin/env python3
"""Fake hermes-dev-team workers for trying the app. No model, no network, no git: it only writes the three files the
real kit writes (runs/<stamp>-<role>.progress.log, runs/<name>.lock, runs.log) into a sandbox scratch folder.

    python tools/fake_worker.py                       # 3 workers in 2 fake projects under ./sandbox, then exit
    python tools/fake_worker.py --workers 5 --speed 0.5 --loop
    python tools/fake_worker.py --sandbox ~/tmp/hdw-sandbox --fail 0.5

Then point the app at the sandbox:  python run.py --root ./sandbox
Each fake run takes about 20-60 s (scaled by --speed), may end PASS or FAIL, and appends a runs.log line.
Ctrl+C removes the locks of runs still going (they show as "NO RESULT stopped or crashed", like a killed worker).
Never point --sandbox at a real project's scratch folder: the fake lines would mix with real history.
"""
import argparse, json, os, pathlib, random, threading, time

ROLES = {
    "dev": [
        "say: I'll read the ticket first, then find where {thing} is computed.",
        "Read .scratch/{feature}/issues/{ticket}",
        "Glob **/*{Thing}*.ts",
        "Grep {thing} in backend/src",
        "Read backend/src/Services/{Thing}Service.ts",
        "say: Found it: {Thing}Service rounds before tax. Fixing the order and adding a test.",
        "Edit backend/src/Services/{Thing}Service.ts",
        "Write backend/src/Services/{Thing}Service.test.ts",
        "?DENIED Edit: package.json is a protected file",
        "Bash yarn --cwd backend typecheck",
        "?exit!=0 Bash: error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.",
        "Edit backend/src/Services/{Thing}Service.ts",
        "Bash yarn --cwd backend typecheck",
        "say: Typecheck passes. Committing.",
        "Bash git add -A",
        'Bash git commit -m "fix({feature}): {thing} rounds after tax"',
    ],
    "reviewer": [
        "say: Reviewing the batch diff against the spec and the standards.",
        "Bash python kit/git-ro.py diff main...HEAD --stat",
        "Read .scratch/{feature}/spec.md",
        "Read backend/src/Services/{Thing}Service.ts",
        "Grep round\\( in backend/src",
        "say: The fix is right; checking the other callers of {thing}.",
        "Read backend/src/Reports/{Thing}Report.ts",
        "Bash yarn --cwd backend typecheck",
        "say: One report still rounds early; writing it up as a spec finding.",
        "Write .scratch/{feature}/review-1.md",
    ],
    "docs": [
        "say: Comparing the merged diff with CONTEXT.md and the glossary.",
        "Bash python kit/git-ro.py diff main...HEAD --stat",
        "Read CONTEXT.md",
        "Read .scratch/{feature}/decisions.md",
        "say: Two drift items: the glossary has no entry for '{thing}', and the README example is stale.",
        "Edit docs/dev-notes.md",
        "Write .scratch/{feature}/drift.md",
    ],
    "researcher": [
        "say: Looking at how the old app computed {thing}.",
        "Read .scratch/research/{feature}/history.txt",
        "Grep {thing} in old/app",
        "Read old/app/Models/{Thing}.php",
        "say: The old code caps carry-over at 6 days; that rule is not in the client docs.",
        "Read old/docs/rules.md",
        "Write .scratch/research/{feature}/findings.md",
    ],
}
THINGS = ["invoice total", "leave balance", "fuel usage", "payroll tax", "stock opname", "contract hours"]
VERDICTS = {
    "dev": (["PASS {sha}"], ["FAIL dirty tree", "FAIL tests failed: 2 of 41", "FAIL could not delete a file (Bash denied)"]),
    "reviewer": (["PASS"], ["FAIL 1 spec, 0 standards: one report still rounds before tax",
                            "FAIL 0 spec, 2 standards: duplicated helper in two services"]),
    "docs": (["PASS {n} drift items"], ["FAIL glossary is read-only"]),
    "researcher": (["PASS findings with {n} citations"], ["FAIL source repo not found"]),
}


def one_run(scratch, role, lockname, speed, fail_rate, stop):
    thing = random.choice(THINGS)
    ctx = {"thing": thing, "Thing": thing.title().replace(" ", ""), "feature": thing.replace(" ", "-") + "-fix",
           "ticket": f"{random.randint(1, 9):02d}-{thing.replace(' ', '-')}.md"}
    ticket = ctx["ticket"] if role == "dev" else "-"
    runs = scratch / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    while True:                                     # unique stamp per role: the run id is <stamp>-<role>
        stamp = time.strftime("%Y%m%d-%H%M%S")
        if not (runs / f"{stamp}-{role}.progress.log").exists():
            break
        time.sleep(1)
    lock = runs / lockname
    lock.write_text(json.dumps({"launcher_pid": os.getpid(), "worker_pid": os.getpid(), "role": role, "ticket": ticket,
                                "feature": ctx["feature"], "repo": scratch.parent.name, "stamp": stamp}), encoding="utf-8")
    t0, steps, denials = time.time(), [], 0
    for s in ROLES[role]:
        if s.startswith("?"):                       # optional line: a denial or a failed command, sometimes
            if random.random() < 0.5:
                continue
            s = s[1:]
        steps.append(s.format(**ctx))
    try:
        with open(runs / f"{stamp}-{role}.progress.log", "w", encoding="utf-8") as f:
            for s in steps:
                if stop.is_set():
                    return
                denials += s.startswith("DENIED")
                f.write(f"  [{round(time.time() - t0):>4}s] {s}\n")
                f.flush()
                time.sleep(random.uniform(1.0, 4.0) * speed)
        ok = random.random() >= fail_rate
        verdict = random.choice(VERDICTS[role][0 if ok else 1]).format(sha=f"{random.getrandbits(32):08x}",
                                                                       n=random.randint(2, 9))
        secs = round(time.time() - t0)
        with open(scratch / "runs.log", "a", encoding="utf-8") as f:
            f.write("\t".join([stamp, role, random.choice(["sonnet", "haiku"]), verdict, f"turns={len(steps) + 3}",
                               f"{secs}s", f"out={random.randint(900, 9000)}", f"list$={random.uniform(0.02, 0.4):.4f}",
                               f"denials={denials}", f"{runs.as_posix()}/{stamp}-{role}.json", f"feature={ctx['feature']}",
                               "test=yarn --cwd backend typecheck", "in=12", "cw=30000", "cr=200000",
                               f"repo={scratch.parent.name}", "backend=fake", f"ticket={ticket}"]) + "\n")
        print(f"  done  {scratch.parent.name:<14} {role:<10} {verdict}", flush=True)
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


def lane(scratch, role, lockname, a, stop):
    while not stop.is_set():
        print(f"  start {scratch.parent.name:<14} {role}", flush=True)
        one_run(scratch, role, lockname, a.speed, a.fail, stop)
        if not a.loop:
            return
        stop.wait(random.uniform(2, 6))


def main():
    ap = argparse.ArgumentParser(description="Fake workers for hermes-dev-watch (no model).")
    ap.add_argument("--sandbox", default="sandbox", help="folder for the fake projects (default ./sandbox)")
    ap.add_argument("--workers", type=int, default=3, help="workers at once (default 3)")
    ap.add_argument("--projects", type=int, default=2, help="fake projects (default 2)")
    ap.add_argument("--speed", type=float, default=1.0, help="delay multiplier; 0.3 = fast (default 1)")
    ap.add_argument("--fail", type=float, default=0.3, help="share of runs that FAIL (default 0.3)")
    ap.add_argument("--loop", action="store_true", help="start a new run whenever one ends, until Ctrl+C")
    a = ap.parse_args()
    root = pathlib.Path(a.sandbox).expanduser().resolve()
    names = ["shop-api", "payroll-web", "fleet-app", "docs-site", "mobile-client"][:max(1, min(a.projects, 5))]
    lanes, roles = [], list(ROLES)
    for i in range(a.workers):                      # one lock per lane: the app shows every live runs/*.lock
        scratch = root / names[i % len(names)] / ".scratch"
        lanes.append((scratch, roles[i % len(roles)], f"fake-{i}.lock"))
    print(f"FAKE sandbox={root}  workers={a.workers}  (open the app with: python run.py --root {root})", flush=True)
    stop = threading.Event()
    ts = [threading.Thread(target=lane, args=(*ln, a, stop), daemon=True) for ln in lanes]
    for i, t in enumerate(ts):
        t.start()
        time.sleep(0.6 if i < len(ts) - 1 else 0)
    try:
        while any(t.is_alive() for t in ts):
            time.sleep(0.3)
    except KeyboardInterrupt:
        stop.set()
        for t in ts:
            t.join(2)
        for _, _, name in lanes:
            for p in root.glob(f"*/.scratch/runs/{name}"):
                p.unlink(missing_ok=True)
        print("FAKE stopped; unfinished runs show as NO RESULT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
