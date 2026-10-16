#!/usr/bin/env python3
"""The run-file contract with hermes-dev-team, from the watcher's side. Stdlib only; never starts the window.

    python tests/contract.py [<hermes-dev-team checkout>]

Without an argument: the reader on hand-made files (format versions, role names, a run id that tries to leave
runs/). With the kit's checkout: also the kit's own samples (tests/fixtures/watch/, written by its real launcher code;
spec in its docs/watch-contract.md), so a kit change this watcher cannot read fails here.
Last line: `<n>/<total> checks passed`; exit 0 only when all pass.
"""
import json, pathlib, shutil, sys, tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from hermes_dev_watch import core  # noqa: E402

results = []


def check(name, ok, detail=None):
    results.append(bool(ok))
    print(("PASS " if ok else "FAIL ") + name)
    if not ok and detail is not None:
        print("      " + str(detail)[-1500:])


def line(stamp, role, verdict="PASS ok", extra=()):
    return "\t".join([stamp, role, "sonnet", verdict, "turns=3", "9s", "list$=0.01", "denials=0", "feature=f",
                      "repo=r", "backend=claude", "ticket=-", *extra]) + "\n"


def local_checks(root):
    s = root / "p" / ".scratch"
    (s / "runs").mkdir(parents=True)
    (s / "runs.log").write_text(line("20261016-100000", "dev") + line("20261016-100100", "dev", extra=["fmt=1"])
                                + line("20261016-100200", "fix-dev") + line("20261016-100300", "dev2"),
                                encoding="utf-8")
    st = core.project_state("p", s)
    ids = [r["id"] for r in st["runs"]]
    check("a line without fmt and a line with fmt=1 both read; project format 1, no warning",
          "20261016-100000-dev" in ids and "20261016-100100-dev" in ids and st["fmt"] == 1
          and not st["newer_format"], st)
    check("role names with `-` and digits are listed (fix-dev, dev2)",
          "20261016-100200-fix-dev" in ids and "20261016-100300-dev2" in ids, ids)
    for bad in ("20261016-100000-../../x", "20261016-100000-a/b", "20261016-100000-a.b", "20261016-100000-Dev", "x"):
        check(f"progress refuses run id {bad!r}", core.progress(s, bad, 0) is None)
    with open(s / "runs.log", "a", encoding="utf-8") as f:
        f.write(line("20261016-100400", "dev", extra=["fmt=2", "newfield=x"]))
    st = core.project_state("p", s)
    check(f"a fmt above KNOWN_FORMAT ({core.KNOWN_FORMAT}) -> newer_format, run still listed",
          st["newer_format"] and st["fmt"] == 2 and any(r["id"] == "20261016-100400-dev" for r in st["runs"]), st)
    s2 = root / "q" / ".scratch"
    (s2 / "runs").mkdir(parents=True)
    import os
    (s2 / "runs" / "worker.lock").write_text(json.dumps({"launcher_pid": os.getpid(), "role": "dev",
                                                         "stamp": "20261016-110000", "fmt": 3}), encoding="utf-8")
    st = core.project_state("q", s2)
    check("a live lock with a newer fmt -> newer_format", st["newer_format"] and st["fmt"] == 3 and st["live"] == 1, st)
    check("fmt_of: absent -> 1, junk -> 0", core.fmt_of(None) == 1 and core.fmt_of("x") == 0 and core.fmt_of("2") == 2)


def kit_checks(kit):
    fx = kit / "tests" / "fixtures" / "watch"
    if not (fx / "runs.log").is_file():
        check(f"kit samples present in {fx.as_posix()}", False); return
    st = core.project_state("kit", fx)
    by = {r["id"]: r for r in st["runs"]}
    check("kit samples: 3 runs, by id",
          sorted(by) == ["20261016-120000-dev", "20261016-120500-researcher", "20261016-121000-docs"], sorted(by))
    dev = by.get("20261016-120000-dev", {})
    check("kit samples: dev run fields (verdict, turns, secs, cost, ticket, feature, repo, backend)",
          (dev.get("verdict"), dev.get("turns"), dev.get("secs"), dev.get("cost"), dev.get("ticket"),
           dev.get("feature"), dev.get("repo"), dev.get("backend"))
          == ("PASS 1a2b3c4", "18", "22", 0.1234, "01-mul.md", "calc", "proj", "claude"), dev)
    check(f"kit samples: format {st['fmt']} is one this watcher knows (<= {core.KNOWN_FORMAT})",
          not st["newer_format"], st["fmt"])
    p = core.progress(fx, "20261016-120000-dev", 0) or {}
    check("kit samples: progress log read (say, tool, DENIED lines)",
          all(x in p.get("text", "") for x in ("say: ", "Read calc.py", "DENIED Bash:")), p)
    lock = json.loads((fx / "runs" / "worker.lock").read_text(encoding="utf-8"))
    check("kit samples: the lock has every field the watcher reads",
          all(k in lock for k in ("launcher_pid", "worker_pid", "role", "ticket", "feature", "repo", "stamp")), lock)


def main():
    root = pathlib.Path(tempfile.mkdtemp(prefix="hdw-contract-")).resolve()
    try:
        local_checks(root)
        if len(sys.argv) > 1:
            kit_checks(pathlib.Path(sys.argv[1]).resolve())
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print(f"{sum(results)}/{len(results)} checks passed")
    return 0 if results and all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
