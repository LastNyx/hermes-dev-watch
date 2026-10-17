"""Self-update from GitHub Releases (design: docs/open/auto-update.md). Stdlib only.

check()  reads the latest release (one unauthenticated api.github.com call) and says whether it is newer.
apply()  downloads this platform's asset next to the running binary, checks its SHA-256 against the digest GitHub
         reports, swaps it in (running binary -> <name>.old, download -> <name>), starts it, and returns; the caller
         quits. The new binary deletes <name>.old on start (cleanup_old).
Running from source (no sys.frozen) never replaces files.
"""
import hashlib, json, os, pathlib, re, subprocess, sys, threading, time, urllib.request

REPO = "LastNyx/hermes-dev-watch"
REPO_URL = f"https://github.com/{REPO}"
# HDW_UPDATE_API: tests point this at a local fake server; it is never set in normal use.
API = os.environ.get("HDW_UPDATE_API") or f"https://api.github.com/repos/{REPO}/releases/latest"
ASSETS = {"win32": "hermes-dev-watch-windows-x64.exe", "linux": "hermes-dev-watch-linux-x64"}
UA = {"User-Agent": "hermes-dev-watch", "Accept": "application/vnd.github+json"}


def parse_version(s):
    """'v0.3.6' or '0.3.6' -> (0, 3, 6); anything else -> None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(s or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def asset_name(platform=None):
    p = platform or sys.platform
    return ASSETS.get("linux" if p.startswith("linux") else p)


def frozen():
    """True in a PyInstaller binary, the only case where the updater may replace a file."""
    return bool(getattr(sys, "frozen", False))


def check(current, api=None, platform=None, timeout=10):
    """{"current", "latest", "newer", "asset": {name, url, digest} | None, "error"?}. Never raises."""
    out = {"current": current, "latest": None, "newer": False, "asset": None}
    try:
        req = urllib.request.Request(api or API, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rel = json.loads(r.read().decode("utf-8"))
    except Exception as e:                                   # offline, rate limit, bad JSON
        return {**out, "error": f"could not reach GitHub: {e}"}
    tag, cur = rel.get("tag_name"), parse_version(current)
    latest = parse_version(tag)
    if latest is None or cur is None:
        return {**out, "error": f"unreadable version: release {tag!r}, this build {current!r}"}
    out["latest"], out["newer"] = tag, latest > cur
    want = asset_name(platform)
    for a in rel.get("assets") or []:
        if a.get("name") == want:
            out["asset"] = {"name": want, "url": a.get("browser_download_url"), "digest": a.get("digest")}
    if out["newer"] and not out["asset"]:
        out["error"] = f"release {tag} has no {want}"
    return out


def download(asset, dest, timeout=60):
    """Download to dest and check SHA-256 against the release digest; on any failure dest is removed and an error
    string returned (None = ok)."""
    digest = str(asset.get("digest") or "")
    if not digest.startswith("sha256:") or not asset.get("url"):
        return "the release gives no sha256 digest for this file; not updating"
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(asset["url"], headers={"User-Agent": UA["User-Agent"]})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
            for chunk in iter(lambda: r.read(1 << 16), b""):
                h.update(chunk)
                f.write(chunk)
    except Exception as e:
        _rm(dest)
        return f"download failed: {e}"
    if h.hexdigest() != digest.split(":", 1)[1].lower():
        _rm(dest)
        return "downloaded file does not match the release's sha256; not updating"
    return None


def swap(exe, new):
    """running exe -> exe.old, new -> exe. Windows allows renaming a running exe, not overwriting it. If the second
    rename fails, the first is undone. Returns the .old path."""
    exe, new = pathlib.Path(exe), pathlib.Path(new)
    old = exe.with_name(exe.name + ".old")
    _rm(old)                                                 # a leftover from an update that never started
    os.replace(exe, old)
    try:
        os.replace(new, exe)
    except OSError:
        os.replace(old, exe)
        raise
    if not sys.platform.startswith("win"):
        exe.chmod(0o755)
    return old


def apply(info, exe=None, argv=None, launch=True):
    """Download, verify, swap and start the new binary. Returns {"ok": True} (caller quits) or {"error": ...}."""
    if not frozen() and exe is None:
        return {"error": "running from source: git pull"}
    if not (info and info.get("newer") and info.get("asset")):
        return {"error": "no newer release to install"}
    exe = pathlib.Path(exe or sys.executable).resolve()
    new = exe.with_name(exe.name + ".new")
    err = download(info["asset"], new)
    if err:
        return {"error": err}
    try:
        swap(exe, new)
    except OSError as e:
        _rm(new)
        return {"error": f"could not replace {exe.name}: {e}"}
    if launch:
        env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}   # the new binary must not reuse our _MEI folder
        subprocess.Popen([str(exe), *(sys.argv[1:] if argv is None else argv)], env=env, close_fds=True)
    return {"ok": True, "installed": info["latest"]}


def cleanup_old(exe=None, tries=20, wait=0.5):
    """Delete <exe>.old (and a stale .new) left by an update. The old process may still be exiting, so retry in the
    background for a few seconds."""
    if exe is None and not frozen():
        return None
    exe = pathlib.Path(exe or sys.executable).resolve()
    paths = [exe.with_name(exe.name + s) for s in (".old", ".new")]

    def run():
        for _ in range(tries):
            for p in paths:
                _rm(p)
            if not any(p.exists() for p in paths):
                return
            time.sleep(wait)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def _rm(p):
    try:
        pathlib.Path(p).unlink()
    except OSError:                                          # missing, or still held by the exiting process
        pass
