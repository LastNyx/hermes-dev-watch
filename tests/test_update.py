"""Self-update (hermes_dev_watch/update.py) against a fake GitHub releases server on 127.0.0.1. Stdlib only; never
starts the window and never touches the real binary.

    python -m unittest tests.test_update -v
"""
import hashlib, http.server, json, os, pathlib, sys, tempfile, threading, unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from hermes_dev_watch import core, update  # noqa: E402

BODY = b"new binary bytes\n" * 100
WIN, LINUX = update.ASSETS["win32"], update.ASSETS["linux"]


class Fake(http.server.BaseHTTPRequestHandler):
    release = {}                                            # set per test; served at /latest

    def do_GET(self):
        if self.path == "/latest":
            data = json.dumps(Fake.release).encode()
        elif self.path.startswith("/dl/"):
            data = BODY
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Update(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="hdw-update-")
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name).resolve()

    def release(self, tag, digest=None, names=(WIN, LINUX)):
        d = digest or "sha256:" + hashlib.sha256(BODY).hexdigest()
        Fake.release = {"tag_name": tag, "assets": [{"name": n, "browser_download_url": f"{self.base}/dl/{n}",
                                                     "digest": d} for n in names]}

    def check(self, current="0.3.6", platform="win32"):
        return update.check(current, api=f"{self.base}/latest", platform=platform)

    def test_versions(self):
        self.assertEqual(update.parse_version("v0.3.10"), (0, 3, 10))
        self.assertIsNone(update.parse_version("v0.3"))
        self.assertIsNone(update.parse_version("latest"))
        self.assertGreater(update.parse_version("v0.3.10"), update.parse_version("0.3.9"))   # not a string compare

    def test_newer_release_picks_this_platforms_asset(self):
        self.release("v0.3.7")
        r = self.check()
        self.assertTrue(r["newer"])
        self.assertEqual((r["latest"], r["asset"]["name"]), ("v0.3.7", WIN))
        self.assertEqual(self.check(platform="linux")["asset"]["name"], LINUX)

    def test_same_or_older_is_not_newer(self):
        for tag in ("v0.3.6", "v0.3.5", "v0.2.9"):
            self.release(tag)
            self.assertFalse(self.check()["newer"], tag)

    def test_bad_tag_is_an_error_not_an_update(self):
        self.release("nightly")
        r = self.check()
        self.assertFalse(r["newer"])
        self.assertIn("unreadable version", r["error"])

    def test_missing_asset(self):
        self.release("v0.3.7", names=(LINUX,))
        r = self.check()
        self.assertTrue(r["newer"])
        self.assertIsNone(r["asset"])
        self.assertIn("has no", r["error"])
        self.assertIn("no newer release", update.apply(r, exe=self.dir / "x.exe", launch=False)["error"])

    def test_offline(self):
        r = update.check("0.3.6", api="http://127.0.0.1:9/latest", timeout=2)
        self.assertFalse(r["newer"])
        self.assertIn("could not reach GitHub", r["error"])

    def test_apply_swaps_and_keeps_old(self):
        exe = self.dir / "hermes-dev-watch.exe"
        exe.write_bytes(b"old binary")
        self.release("v0.3.7")
        r = update.apply(self.check(), exe=exe, launch=False)
        self.assertEqual(r, {"ok": True, "installed": "v0.3.7"})
        self.assertEqual(exe.read_bytes(), BODY)
        self.assertEqual((self.dir / "hermes-dev-watch.exe.old").read_bytes(), b"old binary")
        self.assertFalse((self.dir / "hermes-dev-watch.exe.new").exists())
        update.cleanup_old(exe, tries=1).join()
        self.assertFalse((self.dir / "hermes-dev-watch.exe.old").exists())

    def test_digest_mismatch_changes_nothing(self):
        exe = self.dir / "hermes-dev-watch.exe"
        exe.write_bytes(b"old binary")
        self.release("v0.3.7", digest="sha256:" + "0" * 64)
        r = update.apply(self.check(), exe=exe, launch=False)
        self.assertIn("does not match", r["error"])
        self.assertEqual(exe.read_bytes(), b"old binary")
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["hermes-dev-watch.exe"])

    def test_no_digest_is_refused(self):
        exe = self.dir / "hermes-dev-watch.exe"
        exe.write_bytes(b"old binary")
        self.release("v0.3.7", digest="-")
        self.assertIn("no sha256", update.apply(self.check(), exe=exe, launch=False)["error"])
        self.assertEqual(exe.read_bytes(), b"old binary")

    def test_from_source_never_replaces(self):
        self.assertFalse(update.frozen())                    # the test runs from source
        self.release("v0.3.7")
        self.assertIn("running from source", update.apply(self.check())["error"])
        self.assertIsNone(update.cleanup_old())

    def test_swap_undoes_the_first_rename_on_failure(self):
        exe = self.dir / "a.exe"
        exe.write_bytes(b"old")
        with self.assertRaises(OSError):
            update.swap(exe, self.dir / "missing.new")
        self.assertEqual(exe.read_bytes(), b"old")
        self.assertFalse((self.dir / "a.exe.old").exists())

    def test_config_check_updates(self):
        p = self.dir / "config.json"
        self.assertTrue(core.load_config(p)["check_updates"])               # no file: on
        core.save_config({"roots": [], "scratch": [], "check_updates": False}, p)
        self.assertFalse(core.load_config(p)["check_updates"])
        p.write_text(json.dumps({"roots": ["x"]}), encoding="utf-8")        # an old config: on
        self.assertTrue(core.load_config(p)["check_updates"])


if __name__ == "__main__":
    unittest.main()
