"""The run-file contract with hermes-dev-team, from the watcher's side. Stdlib only; never starts the window.

    python -m unittest discover -s tests -v
    python tests/test_contract.py [<hermes-dev-team checkout>]

Hand-made files always run. The kit's samples (tests/fixtures/watch/, spec in its docs/watch-contract.md) run when
HDW_KIT_DIR names a hermes-dev-team checkout (a path argument sets it); otherwise that class is skipped.
"""
import json, os, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from hermes_dev_watch import core  # noqa: E402


def line(stamp, role, verdict="PASS ok", extra=()):
    return "\t".join([stamp, role, "sonnet", verdict, "turns=3", "9s", "list$=0.01", "denials=0", "feature=f",
                      "repo=r", "backend=claude", "ticket=-", *extra]) + "\n"


class HandMadeFiles(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hdw-contract-")
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name).resolve()
        self.s = self.root / "p" / ".scratch"
        (self.s / "runs").mkdir(parents=True)
        (self.s / "runs.log").write_text(
            line("20261016-100000", "dev") + line("20261016-100100", "dev", extra=["fmt=1"])
            + line("20261016-100200", "fix-dev") + line("20261016-100300", "dev2"), encoding="utf-8")

    def test_fmt_absent_and_fmt_1_both_read(self):
        st = core.project_state("p", self.s)
        ids = [r["id"] for r in st["runs"]]
        self.assertIn("20261016-100000-dev", ids)
        self.assertIn("20261016-100100-dev", ids)
        self.assertEqual(st["fmt"], 1)
        self.assertFalse(st["newer_format"])

    def test_role_names_with_dash_and_digits_are_listed(self):
        ids = [r["id"] for r in core.project_state("p", self.s)["runs"]]
        self.assertIn("20261016-100200-fix-dev", ids)
        self.assertIn("20261016-100300-dev2", ids)

    def test_progress_refuses_bad_run_ids(self):
        for bad in ("20261016-100000-../../x", "20261016-100000-a/b", "20261016-100000-a.b",
                    "20261016-100000-Dev", "x"):
            with self.subTest(run_id=bad):
                self.assertIsNone(core.progress(self.s, bad, 0))

    def test_non_string_run_ids_are_refused(self):
        for bad in (5, [], {}, True, None):
            with self.subTest(run_id=bad):
                self.assertIsNone(core.search_log(self.s, bad, "x"))
                self.assertIsNone(core.progress(self.s, bad, 0))

    def test_search_log(self):
        rid = "20261016-100000-dev"
        self.assertEqual(core.search_log(self.s, rid, "x"), {"lines": [], "total": 0, "capped": False})
        self.assertIsNone(core.search_log(self.s, "../x", "x"))
        log = self.s / "runs" / f"{rid}.progress.log"
        log.write_bytes(b"[10:00] Alpha a.b\n\n  \nplain axb\r\n[10:01] ALPHA (x)\nbad \xff alpha\n")
        r = lambda t: core.search_log(self.s, rid, t)
        self.assertEqual(r("alpha"), {"lines": [0, 2, 3], "total": 3, "capped": False})
        self.assertEqual(r(" a.b ")["lines"], [0])
        self.assertEqual(r("(x)")["lines"], [2])
        for t in ("", "  ", None, 5):
            self.assertEqual(r(t), {"lines": [], "total": 0, "capped": False})
        log.write_text("hit\n" * 1005, encoding="utf-8")
        big = r("HIT")
        self.assertEqual((len(big["lines"]), big["total"], big["capped"]), (1000, 1005, True))
        log.write_text("a" * 250 + "\n" + "a" * 200 + "\n", encoding="utf-8")
        self.assertEqual(r("a" * 300)["lines"], [0, 1])

    def test_progress_crlf_log_reads_as_lf_in_small_reads(self):
        lines = ["alpha one", "beta\rtwo", "gamma three", "delta"]
        (self.s / "runs" / "20261016-100000-dev.progress.log").write_bytes(
            "".join(x + "\r\n" for x in lines).encode())
        size = (self.s / "runs" / "20261016-100000-dev.progress.log").stat().st_size
        text, off = "", 0
        orig = core.CHUNK
        core.CHUNK = 14
        try:
            for _ in range(50):
                p = core.progress(self.s, "20261016-100000-dev", off)
                text, off = text + p["text"], p["offset"]
                if off == size:
                    break
        finally:
            core.CHUNK = orig
        self.assertEqual(text, "".join(x + "\n" for x in lines))
        self.assertEqual(off, size)

    def test_fmt_above_known_format_flags_newer_but_lists_run(self):
        with open(self.s / "runs.log", "a", encoding="utf-8") as f:
            f.write(line("20261016-100400", "dev", extra=["fmt=2", "newfield=x"]))
        st = core.project_state("p", self.s)
        self.assertTrue(st["newer_format"])
        self.assertEqual(st["fmt"], 2)
        self.assertTrue(any(r["id"] == "20261016-100400-dev" for r in st["runs"]))

    def test_live_lock_with_newer_fmt_flags_newer_format(self):
        s2 = self.root / "q" / ".scratch"
        (s2 / "runs").mkdir(parents=True)
        (s2 / "runs" / "worker.lock").write_text(
            json.dumps({"launcher_pid": os.getpid(), "role": "dev", "stamp": "20261016-110000", "fmt": 3}),
            encoding="utf-8")
        st = core.project_state("q", s2)
        self.assertTrue(st["newer_format"])
        self.assertEqual(st["fmt"], 3)
        self.assertEqual(st["live"], 1)

    def test_run_filter(self):
        import datetime
        from unittest import mock
        now = datetime.datetime(2026, 10, 16, 12, 0)
        def r(stamp, role, verdict, **kw):
            return {"id": f"{stamp}-{role}", "stamp": stamp, "role": role, "verdict": verdict, **kw}
        runs = [r("20261016-100000", "dev", "PASS ok", ticket="T1", model="Sonnet"),
                r("20261010-100000", "review", "FAIL bad", project="Proj"),
                r("20260920-100000", "dev", "ERROR x"),
                r("20261016-090000", "dev", "NO RESULT stopped"),
                r("20261016-080000", "dev", None, live=True)]
        ids = lambda flt: [x["id"] for x in core.filter_runs(runs, flt, now)]
        all_ids = [x["id"] for x in runs]
        for bad in (None, "x", [], {}, {"zzz": 1}, {"verdict": "pass", "role": 5, "days": "9", "q": 7},
                    {"verdict": ["bogus"], "role": ["Bad/x"]}):
            self.assertEqual(ids(bad), all_ids)
        self.assertEqual(ids({"q": "x" * 500}), [])
        self.assertEqual(ids({"verdict": ["pass"]}), [all_ids[0]])
        self.assertEqual(ids({"verdict": ["fail"]}), all_ids[1:3])
        self.assertEqual(ids({"verdict": ["none", "running"]}), all_ids[3:])
        self.assertEqual(ids({"role": ["review"]}), [all_ids[1]])
        self.assertEqual(ids({"days": "today"}), [all_ids[0], all_ids[3], all_ids[4]])
        self.assertEqual(ids({"days": "7"}), all_ids[:2] + all_ids[3:])
        self.assertEqual(ids({"days": "30"}), all_ids)
        self.assertEqual(ids({"days": "all"}), all_ids)
        self.assertEqual(ids({"q": "SONNET"}), [all_ids[0]])
        self.assertEqual(ids({"q": "proj", "role": ["review"], "days": "7"}), [all_ids[1]])
        with open(self.s / "runs.log", "a", encoding="utf-8") as f:
            f.write(line("20200101-000000", "review", "FAIL old"))
        (self.s / "runs" / "worker.lock").write_text(
            json.dumps({"launcher_pid": os.getpid(), "role": "dev", "stamp": "20261016-120000"}), encoding="utf-8")
        with mock.patch.object(core, "MAX_RUNS", 2):
            st = core.project_state("p", self.s, {"verdict": ["fail"]}, now)
        self.assertEqual([x["id"] for x in st["runs"]], ["20200101-000000-review"])
        st = core.project_state("p", self.s, {"verdict": ["pass"]}, now)
        self.assertEqual(st["total"], 4)
        with mock.patch.object(core, "MAX_RUNS", 2):
            st = core.project_state("p", self.s, {"verdict": ["pass"]}, now)
        self.assertEqual((len(st["runs"]), st["total"]), (2, 4))
        self.assertEqual([x["id"] for x in st["live_runs"]], ["20261016-120000-dev"])
        self.assertEqual(st["roles"], ["dev", "dev2", "fix-dev", "review"])
        self.assertEqual(st["run_count"], 6)
        self.assertEqual(core.project_state("p", self.s, None, now)["run_count"], 6)
        self.assertEqual(st["today"], {"runs": 4, "pass": 4, "cost": 0.04, "planner": 0})

    def test_planner_lines_left_out_of_today(self):
        import datetime
        with open(self.s / "runs.log", "a", encoding="utf-8") as f:
            f.write(line("20261016-100400", "planner", "NOTE status 01 review")
                    + line("20261016-100500", "planner", "FAIL verify 01: blank"))
        st = core.project_state("p", self.s, None, datetime.datetime(2026, 10, 16, 12, 0))
        self.assertEqual(st["today"], {"runs": 4, "pass": 4, "cost": 0.04, "planner": 2})
        self.assertIn("planner", st["roles"])
        self.assertEqual(len(st["runs"]), 6)

    def test_open_run_comes_back_fresh_whatever_the_filter(self):
        lock = self.s / "runs" / "worker.lock"
        lock.write_text(json.dumps({"launcher_pid": os.getpid(), "role": "dev", "stamp": "20261016-120000"}),
                        encoding="utf-8")
        hide = {"verdict": ["pass"]}
        st = core.project_state("p", self.s, hide, open_run="20261016-120000-dev")
        self.assertNotIn("20261016-120000-dev", [r["id"] for r in st["runs"]])
        self.assertTrue(st["open"]["live"])
        self.assertEqual(st["open"]["project"], "p")
        lock.unlink()
        with open(self.s / "runs.log", "a", encoding="utf-8") as f:
            f.write(line("20261016-120000", "dev", "FAIL late"))
        st = core.project_state("p", self.s, hide, open_run="20261016-120000-dev")
        self.assertEqual(st["open"]["verdict"], "FAIL late")
        self.assertFalse(st["open"].get("live"))
        for bad in (None, 5, ["x"], {}, "x", "20261016-120000-../x", "20261016-999999-dev"):
            self.assertIsNone(core.project_state("p", self.s, open_run=bad)["open"])

    def test_run_stats(self):
        import datetime
        from unittest import mock
        now = datetime.datetime(2026, 10, 16, 12, 0)
        def run(stamp, role="dev", verdict="PASS ok", live=False):
            return {"id": f"{stamp}-{role}", "stamp": stamp, "role": role, "verdict": verdict, "live": live}
        runs = [run("20261016-100000"), run("20261016-110000", "dev", "FAIL x"), run("20261016-120000", "dev", None),
                run("20261016-130000", "dev", "PASS", live=True), run("20261016-140000", "planner"),
                run("20261017-100000"), run("20260917-100000", "review"), run("20260916-100000", "review"),
                run("20260530-100000", "review"), run("20260529-100000", "review"), run("bad", "review"),
                run(None, "review")]
        st = core.run_stats(runs, now)
        self.assertEqual(st["by_role"], {"dev": {"runs": 3, "pass": 1}, "review": {"runs": 1, "pass": 1}})
        self.assertEqual(st["by_day"], {"20261016": 3, "20260917": 1, "20260916": 1, "20260530": 1})
        self.assertEqual(st["days"], 140)
        with open(self.s / "runs.log", "a", encoding="utf-8") as f:
            f.write(line("20200101-000000", "review", "FAIL old"))
        with mock.patch.object(core, "MAX_RUNS", 2):
            st = core.project_state("p", self.s, {"verdict": ["fail"]}, now)
        self.assertEqual(len(st["runs"]), 1)
        self.assertEqual(st["stats"]["by_role"], {"dev": {"runs": 2, "pass": 2}, "fix-dev": {"runs": 1, "pass": 1},
                                                  "dev2": {"runs": 1, "pass": 1}})
        self.assertEqual(st["stats"]["by_day"], {"20261016": 4})

    def test_fmt_of(self):
        self.assertEqual(core.fmt_of(None), 1)
        self.assertEqual(core.fmt_of("x"), 0)
        self.assertEqual(core.fmt_of("2"), 2)


class KitSamples(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kit = os.environ.get("HDW_KIT_DIR")
        if not kit:
            raise unittest.SkipTest("set HDW_KIT_DIR to a hermes-dev-team checkout")
        cls.fx = pathlib.Path(kit).resolve() / "tests" / "fixtures" / "watch"
        if not (cls.fx / "runs.log").is_file():
            raise AssertionError(f"kit samples missing: {(cls.fx / 'runs.log').as_posix()}")
        cls.st = core.project_state("kit", cls.fx)
        cls.by = {r["id"]: r for r in cls.st["runs"]}

    def test_runs_by_id(self):
        self.assertEqual(sorted(self.by), ["20261016-120000-dev", "20261016-120500-researcher",
                                           "20261016-121000-docs", "20261016-121500-planner"])

    def test_planner_line(self):
        pl = self.by.get("20261016-121500-planner", {})
        self.assertEqual((pl.get("role"), pl.get("model"), pl.get("verdict"), pl.get("turns"), pl.get("cost"),
                          pl.get("ticket")),
                         ("planner", "planner", "FAIL verify 01: the sum is blank", "-", None, "01-mul.md"))
        text = (core.progress(self.fx, "20261016-121500-planner", 0) or {}).get("text", "")
        self.assertEqual(text, "")              # kit 0.14.0: planner lines have no progress log

    def test_dev_run_fields(self):
        dev = self.by.get("20261016-120000-dev", {})
        self.assertEqual(
            (dev.get("verdict"), dev.get("turns"), dev.get("secs"), dev.get("cost"), dev.get("ticket"),
             dev.get("feature"), dev.get("repo"), dev.get("backend")),
            ("PASS 1a2b3c4", "18", "22", 0.1234, "01-mul.md", "calc", "proj", "claude"))

    def test_format_is_known(self):
        self.assertFalse(self.st["newer_format"], self.st["fmt"])

    def test_progress_log_read(self):
        text = (core.progress(self.fx, "20261016-120000-dev", 0) or {}).get("text", "")
        for x in ("say: ", "Read calc.py", "DENIED Bash:"):
            self.assertIn(x, text)

    def test_lock_has_every_field_the_watcher_reads(self):
        lock = json.loads((self.fx / "runs" / "worker.lock").read_text(encoding="utf-8"))
        for k in ("launcher_pid", "worker_pid", "role", "ticket", "feature", "repo", "stamp"):
            self.assertIn(k, lock)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        os.environ["HDW_KIT_DIR"] = str(pathlib.Path(sys.argv[1]).resolve())
    unittest.main(argv=[sys.argv[0], "-v"])
