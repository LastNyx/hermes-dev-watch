"""Desktop window (pywebview). The page talks to Python through pywebview's JS bridge: no HTTP server, no port.

Windows: Edge WebView2 (built into Windows 10/11). Linux: GTK + WebKit2GTK 4.1 (system packages).
"""
import argparse, pathlib, shutil, subprocess, sys

import webview

from . import __version__, core

STATIC = pathlib.Path(__file__).resolve().parent / "static"


class Api:
    """Methods the page calls as window.pywebview.api.<name>(...). Every call is read-only except save_config."""

    def __init__(self, projects, cfg_path):
        # underscore names: pywebview does not expose them to the page (it walks public attributes)
        self._projects, self._cfg_path, self._window = projects, cfg_path, None

    def state(self, flt=None, open_run=None):
        o = open_run if isinstance(open_run, dict) else {}          # {"project": id, "run": run id}; bad input = none
        return {"projects": [core.project_state(pid, s, flt, open_run=o.get("run") if o.get("project") == pid else None)
                             for pid, s in sorted(self._projects.get().items())],
                "known_format": core.KNOWN_FORMAT}

    def progress(self, project, run, offset):
        scratch = self._projects.get().get(project)                 # only a known project, never a path from the page
        try:
            offset = max(0, int(offset))
        except (TypeError, ValueError):
            offset = 0
        d = core.progress(scratch, run, offset) if scratch else None
        return d or {"text": "", "offset": 0, "size": 0, "error": "unknown project or run"}

    def get_config(self):
        return {**core.load_config(self._cfg_path), "path": str(self._cfg_path)}

    def save_config(self, cfg):
        clean = {k: [str(x) for x in (cfg or {}).get(k) or [] if str(x).strip()] for k in ("roots", "scratch")}
        core.save_config(clean, self._cfg_path)
        self._projects.set(core.resolve(clean["scratch"]) + self._projects.extra, core.resolve(clean["roots"]))
        return self.get_config()

    def pick_folder(self):
        r = self._window.create_file_dialog(webview.FOLDER_DIALOG) if self._window else None
        return str(r[0]) if r else None

    def notify(self, title, body):
        """Desktop notification when a run ends. Linux: notify-send if present. Elsewhere: the in-app toast only."""
        if sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "-a", "Hermes Dev Watch", str(title)[:120], str(body)[:300]],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hermes-dev-watch", description="Read-only desktop view of hermes-dev-team runs.")
    ap.add_argument("--root", action="append", default=[], help="also scan this folder this session (not saved)")
    ap.add_argument("--scratch", action="append", default=[], help="also watch this scratch folder (not saved)")
    ap.add_argument("--config", default=str(core.CONFIG), help=f"config file (default {core.CONFIG})")
    ap.add_argument("--debug", action="store_true", help="open the web inspector")
    ap.add_argument("--version", action="version", version=__version__)
    a = ap.parse_args(argv)
    cfg_path = pathlib.Path(a.config).expanduser()
    cfg = core.load_config(cfg_path)
    extra_scratch = core.resolve(a.scratch)
    for here in (pathlib.Path.cwd() / ".scratch", pathlib.Path.cwd().parent / ".scratch"):   # a repo or workspace
        if here.is_dir():
            extra_scratch.insert(0, here.resolve())
            break
    projects = core.Projects(core.resolve(cfg["scratch"]) + extra_scratch, core.resolve(cfg["roots"] + a.root))
    projects.extra = extra_scratch            # session-only folders survive a settings save
    api = Api(projects, cfg_path)
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    api._window = webview.create_window(f"Hermes Dev Watch {__version__}", html=html, js_api=api,
                                       width=1320, height=840, min_size=(900, 560), background_color="#0e0f12")
    # Linux: GTK/WebKit directly (pywebview would try Qt first on KDE and log a traceback)
    webview.start(gui="gtk" if sys.platform.startswith("linux") else None, debug=a.debug)
    return 0
