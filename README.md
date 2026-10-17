# hermes-dev-watch

A desktop app (Windows and Linux) for watching [hermes-dev-team](https://github.com/LastNyx/hermes-dev-team) worker
runs live, across every project on the machine.

- **Live**: one card per running worker, in any project, showing its newest progress lines.
- **Runs**: every run grouped by day, with role, ticket, verdict, duration and list cost; a project picker and a run
  filter: verdict (pass / fail / no result / running), role, date (today / 7 / 30 days / all) and text, remembered
  across restarts. The live board, toasts and the header's "today" stats ignore the filter.
- **Planner lines** (kit 0.13.7+): the planner's own checks and notes (`PASS verify 05`, `NOTE fix 13: ...`) are
  runs of role `planner`, with the check's steps as `say:` lines. The header counts them apart (`· N planner`).
- **Run log**: the full progress log as it is written, which can be filtered to `say` / `edit` / `bash` / `denied` /
  `error` lines, and searched (plain text, Enter / Shift+Enter to step, Escape to clear; the first 1000 matches).
- **Finished runs**: an in-app toast when a run ends, plus a desktop notification on Linux (`notify-send`).
- **Settings (⚙)**: add or remove project folders with a folder picker.

The app only reads files. It cannot start or stop a worker (to stop one, use `scratch.py stop` in the kit), and it
opens no network port: the window calls Python directly through pywebview's bridge. The only file it writes is its
own `config.json`.

## Download

Every `v*` tag builds `hermes-dev-watch-windows-x64.exe` and `hermes-dev-watch-linux-x64` and attaches them to the
GitHub release. They need no Python.

- Windows: WebView2 is built into Windows 10/11.
- Linux: needs GTK 3 and WebKit2GTK 4.1 installed on the system (Arch: `webkit2gtk-4.1`; Debian/Ubuntu:
  `gir1.2-webkit2-4.1`).

### Updates (0.3.6 and later)

The app checks the latest GitHub release at startup and from Settings > **Check for updates**. A newer one shows
`vX.Y.Z available - Update` in the header; nothing is downloaded until you click. Update downloads the file next to
the binary, checks its SHA-256 against the digest GitHub lists for the release asset, renames the running binary to
`<name>.old`, puts the new one in its place, starts it and closes the old window. The new version deletes `.old`.
Settings > **Check at startup** (config `check_updates`) turns off the startup check; the button still works.
Running from source, the header says `running from source: git pull` and no file is replaced.

If a new version will not start, `.old` is still there: delete the new binary and rename `<name>.old` back to
`<name>` (Windows: `hermes-dev-watch-windows-x64.exe.old` -> `hermes-dev-watch-windows-x64.exe`).

## Develop

Linux (the venv needs the system PyGObject, hence `--system-site-packages`):

```
uv venv --python /usr/bin/python3 --system-site-packages .venv
uv pip install --python .venv/bin/python -r requirements.txt pyinstaller
.venv/bin/python run.py
```

Windows (PowerShell, Python 3.10+ from python.org):

```
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt pyinstaller
.venv\Scripts\python run.py
```

Options: `--root DIR` and `--scratch DIR` add folders for this session only (not saved), `--config FILE`, `--debug`
(opens the web inspector). Build the one-file app with `pyinstaller hermes-dev-watch.spec`; the result goes to `dist/`.

Layout: `hermes_dev_watch/core.py` reads the files (stdlib only), `app.py` creates the window and the bridge, and
`static/index.html` is the whole UI.

## Fake workers (no AI model)

`tools/fake_worker.py` writes realistic progress logs, locks and `runs.log` lines into a sandbox. It calls no model,
uses no network and touches no git:

```
python tools/fake_worker.py --sandbox sandbox --workers 4 --loop     # Ctrl+C stops
python run.py --root sandbox
```

`--speed 0.3` makes it faster, `--fail 0.5` makes half the runs fail, and `--projects 3` spreads the workers over more
fake projects. Never point `--sandbox` at a real project's scratch folder.

## Projects

The app watches:

- every root and scratch folder in `config.json`. On Linux that is `~/.config/hermes-dev-watch/config.json`; on
  Windows it is `%APPDATA%\hermes-dev-watch\config.json`. The settings screen edits this file.
- `--root` / `--scratch` given on the command line, for that session only
- `./.scratch` or `../.scratch` of the folder it was started from

Under a root, it finds every `.scratch` folder up to 3 levels down that has a `runs.log` or `runs/`. Roots are scanned
again every 15 s, so a new project shows up after its first run.

## File format (the contract with hermes-dev-team)

The kit owns the format: its [docs/watch-contract.md](https://github.com/LastNyx/hermes-dev-team/blob/main/docs/watch-contract.md) is the spec, and its `tests/fixtures/watch/` holds samples written by its real launcher code.
Both CIs check that this watcher reads them: the kit's on every kit push, this repo's on every push here and
weekly (`python tests/test_contract.py <kit checkout>`, or `HDW_KIT_DIR=<kit checkout> python -m
unittest discover -s tests -v`; stdlib only).

| File | Written by (kit) | Format |
|---|---|---|
| `runs.log` | `run-worker.py` `report()`, one line per finished run; the planner's `scratch.py` commands add `planner` lines (kit 0.13.7+, `action=` key) | tab-separated: `stamp`, `role`, `model`, `verdict`, then `turns=`, `<secs>s`, and `key=value` fields (`list$`, `denials`, `feature`, `ticket`, `repo`, `backend`, …) |
| `runs/<stamp>-<role>.progress.log` | `run-worker.py` `stream_worker()`, while the run happens | one line per event: `  [  12s] <text>`. `<text>` is `<Tool> <arg>`, `say: <worker text>` (kit 0.13.2+), `DENIED <tool>: …` or `exit!=0 <tool>: …` |
| `runs/*.lock` | the launcher, while a worker runs | JSON with `launcher_pid`, `worker_pid`, `role`, `ticket`, `feature`, `repo`, `stamp`. The run is live when either pid is alive. Today the kit writes only `worker.lock`; any other `*.lock` (one per repo or role, or the fake workers' `fake-N.lock`) is shown the same way |

`<stamp>` is `YYYYMMDD-HHMMSS`. A run's id is `<stamp>-<role>` (role: lowercase letters, digits and `-`), and that
id links the three files.

Format version: kit 0.13.3+ writes `fmt=<n>` at the end of each `runs.log` line and `"fmt": <n>` in the lock (a
line or lock without it is format 1). When a project shows a format above the one this watcher knows
(`core.KNOWN_FORMAT`), the header says "kit format <n> is newer than this watcher: update hermes-dev-watch" and
the runs are still shown as well as it can. The kit keeps
`runs/` out of the scratch git repo, so a run made on another machine shows its verdict but no log.

## Status

Linux (CachyOS, KDE Wayland, WebKit2GTK 4.1): runs from source and as the PyInstaller binary, tested with fake
workers. Windows: the build is set up in CI but has not been run on a real PC yet. It has not been watched during a
real `claude -p` run yet.

## License

MIT
