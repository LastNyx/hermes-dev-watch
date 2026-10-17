# Changelog

## 0.3.5 - 2026-10-17

- Tests: hermes-dev-team 0.14.0 writes no planner progress log (planner lines are `action=status|decide`, result path
  `-`), so `KitSamples.test_planner_line` expects an empty progress text. `core.py` unchanged.

## 0.3.4 - 2026-10-16

- Planner lines (hermes-dev-team 0.13.7: role `planner`, one line per planner check or note) show as runs with a
  `planner` role chip. The header's "today" runs/pass/fail/cost counts leave them out and show `· N planner`
  separately; before, every `NOTE` line counted as a failure. `core.project_state` `today` gains `planner`.
- Tests: the kit's planner sample is read, and planner lines stay out of `today` (18 tests).

## 0.3.3 - 2026-10-16

Feature filters-search, built by hermes-dev-team dev and reviewer workers (14 tickets, 2 review batches).

- Run filter: `core.filter_runs` and `project_state(flt)` (filter first, then the 200-run cap; `total`,
  `run_count`, `live_runs`, `roles`, `today`), `Api.state(flt, open_run)`, and a filter bar in the page. The run
  open in the detail view comes back from the reader even when the filter hides it.
- Log search: `core.search_log` and `Api.search`; in the page, marks, `n of m`, stepping and wrap, line kinds
  skipped.
- Fixed (older than this feature): on Windows the run log showed every line raw, because progress logs have
  `\r\n` endings; `progress()` now returns `\n`. A non-string run id from the page no longer raises.
- Checked in a browser against the real reader (not the pywebview window); 16 unit tests (11 without a kit checkout).

## 0.3.2 - 2026-10-16

- `tests/test_contract.py` (feature filters-search, ticket 01, by a dev worker): the contract checks under
  unittest; the kit-sample checks run when `HDW_KIT_DIR` points at a hermes-dev-team checkout, else skip.
  `tests/contract.py` removed. CI runs `python -m unittest discover -s tests -v` with `HDW_KIT_DIR` set.

## 0.3.1 - 2026-10-16

- `.github/workflows/release.yml`: actions pinned by commit SHA at the latest release of the same major version
  (checkout v4.4.0, setup-python v5.6.0, upload-artifact v4.6.2, action-gh-release v2.6.2), and the checkout keeps
  no credentials. The workflow can write releases, so a moved tag in an action could publish another binary. Not
  run yet (it runs on a `v*` tag).

## 0.3.0 - 2026-10-16

Follow the kit's run-file format (hermes-dev-team 0.13.3+, its `docs/watch-contract.md`).

- `hermes_dev_watch/core.py`: reads `fmt` from `runs.log` lines and locks (absent = 1); `project_state` returns
  `fmt` and `newer_format` when a project has a format above `KNOWN_FORMAT` (1). Run ids accept roles with digits
  and `-` (`[a-z][a-z0-9-]*`; still no `/` or `.`), so a future role like `fix-dev` is listed, not dropped.
- `hermes_dev_watch/static/index.html`: a header warning "kit format <n> is newer than this watcher: update
  hermes-dev-watch" (the project names in its tooltip). Checked in a browser with a mocked bridge: shown for
  format 2, hidden for 1; a `fix-dev` run is listed.
- `tests/contract.py` (new, stdlib only): 10 checks on hand-made files (format versions, role names, run ids that
  try to leave `runs/`) and 5 on the kit's samples when given a kit checkout. 0.2.0's reader crashes on it.
- `.github/workflows/tests.yml` (new): the contract on Linux and Windows against the kit's `main`, on every push,
  PR and weekly. No secrets.
- `tools/fake_worker.py`: writes `fmt=1` like the kit.

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
