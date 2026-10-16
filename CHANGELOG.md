# Changelog

## 0.2.0 - 2026-10-16

Desktop app for Windows and Linux; the web page mode is gone.

- `hermes_dev_watch/app.py` (new): a pywebview window (WebView2 on Windows, GTK/WebKit2GTK 4.1 on Linux). The page
  calls Python through the JS bridge, so there is no HTTP server and no port. Bridge methods: `state`, `progress`
  (accepts only known projects and valid run ids), `get_config`, `save_config`, `pick_folder`, `notify`.
- `hermes_dev_watch/core.py` (new): the file reader from 0.1.0 (stdlib only), plus `config.json` load and save. The
  config lives in `%APPDATA%` on Windows and `~/.config` on Linux.
- `hermes_dev_watch/static/index.html` (new): the UI, moved out of the Python string. Adds a settings screen (folder
  picker for roots and scratch folders) and a toast when a run ends, which is also a desktop notification on Linux via
  `notify-send`. Fixes for WebKitGTK: the page starts even if the bridge is ready before the script runs, it works
  when `localStorage` throws on `about:blank`, and the project select is dark.
- `watch.py`: removed. `run.py` / `python -m hermes_dev_watch` start the app.
- `tools/fake_worker.py` (new): fake workers that call no model. They write progress logs, locks and `runs.log` lines
  into a sandbox; options for the number of workers, speed, fail rate and looping.
- Build: `hermes-dev-watch.spec` (one file, no console, Qt/Tk excluded) and `.github/workflows/release.yml` (on a
  `v*` tag, builds the Windows `.exe` and the Linux binary and attaches them to the release).
- Tested on Linux only, with fake workers: from source, as the PyInstaller binary (it starts), and in the real GTK
  window with the page state read back. Windows has not been run yet.

## 0.1.0 - 2026-10-16

- `watch.py`: local read-only web page over hermes-dev-team runs (runs.log, runs/*.progress.log, runs/*.lock) across
  projects: live board of running workers, run list by day, filterable run log, project picker, config file.
