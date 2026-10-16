# hermes-dev-watch

A live, read-only view of [hermes-dev-team](https://github.com/LastNyx/hermes-dev-team) worker runs, across every
project on this machine. One stdlib Python file, no dependencies, no build step. It shows a small local web page. You
can open it in the Hermes desktop preview pane, next to the planner chat.

- **Live**: one card for each running worker, in any project, with its newest progress lines.
- **Runs**: every run grouped by day, with role, ticket, verdict, duration and list cost. You can filter by text and
  pick a project.
- **Run log**: the whole progress log, updated as it is written. It can be filtered to `say` / `edit` / `bash` /
  `denied` / `error` lines.

It only reads files: it writes nothing and cannot start or stop a worker (to stop one, use `scratch.py stop` in the
kit). It binds to `127.0.0.1` only.

## Requirements

Any Python 3.7+, no packages. On Windows without a system Python, run it from a Hermes terminal: Hermes' bundled
Python works, and nothing is installed into it.

## Run

```
python watch.py --root ~/Dokumen/projects --root ~/Proyek
```

Then open <http://127.0.0.1:8765>.

The page lists these projects:

- `./.scratch` or `../.scratch` of the current folder (a repo, or a workspace)
- every `--scratch PATH`
- every `.scratch` folder up to 3 levels below each `--root DIR` that has a `runs.log` or `runs/`

Roots are scanned again every 15 s, so a project shows up after its first run without a restart.

To skip the flags, put the roots in `~/.config/hermes-dev-watch/config.json`; flags add to what the file lists:

```json
{"roots": ["~/Dokumen/projects", "~/Proyek"], "port": 8765}
```

## File format (the contract with hermes-dev-team)

The watcher depends on the kit only through three files in a project's scratch folder. If the kit changes one of
them, this file has to change too.

| File | Written by (kit) | Format |
|---|---|---|
| `runs.log` | `run-worker.py` `report()`, one line per finished run | tab-separated: `stamp`, `role`, `model`, `verdict`, then `turns=`, `<secs>s`, and `key=value` fields (`list$`, `denials`, `feature`, `ticket`, `repo`, `backend`, …) |
| `runs/<stamp>-<role>.progress.log` | `run-worker.py` `stream_worker()`, while the run happens | one line per event: `  [  12s] <text>`. `<text>` is `<Tool> <arg>`, `say: <worker text>` (kit 0.13.2+), `DENIED <tool>: …` or `exit!=0 <tool>: …` |
| `runs/*.lock` | the launcher, while a worker runs | JSON with `launcher_pid`, `worker_pid`, `role`, `ticket`, `feature`, `repo`, `stamp`. The run is live when either pid is alive. Today the kit writes only `worker.lock`; more locks (one per repo or role) will show up here with no change |

`<stamp>` is `YYYYMMDD-HHMMSS`. A run's id is `<stamp>-<role>`, and that id links the three files.

The kit keeps `runs/` out of the scratch git repo. A run made on another machine therefore shows its verdict but no
log.

## Status

Tested with fake workers (3 at once in 2 projects), against copies of real `runs.log` and progress logs, in headless
Brave and in the Hermes preview pane, on Linux. Not yet tested on Windows or macOS, and not yet watched during a real
`claude -p` run.

## License

MIT
