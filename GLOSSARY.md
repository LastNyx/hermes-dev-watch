# hermes-dev-watch

A read-only desktop view of the worker runs that hermes-dev-team's kit records in each project's scratch folder.

## Language

**Run**:
One worker's attempt at one job (a ticket, a review, docs, a research), from start to verdict.
_Avoid_: job, task, execution

**Run id**:
The name that ties a run's records together: its start time and its role.
_Avoid_: run key, run name

**Role**:
What kind of worker made a run (dev, reviewer, docs, researcher, or a role added later).
_Avoid_: agent, worker type

**Verdict**:
The one-line outcome the kit recorded when a run ended.
_Avoid_: result, status

**Verdict group**:
The class a run falls into for filtering: pass, fail (a failure or an error), no result (ended without a verdict), or running.
_Avoid_: state, outcome

**Live run**:
A run whose worker is still running now.
_Avoid_: active run, current run

**Project**:
One scratch folder the watcher shows, named after the repo or workspace it belongs to.
_Avoid_: repo, workspace (a project may hold several repos)

**Progress log**:
The lines a run writes while it works: tool calls, what the worker says, denials, failures.
_Avoid_: transcript, run log

**Line kind**:
The class of one progress-log line: say, edit, bash, denied, error, or other.
_Avoid_: line type, log level

**Run filter**:
The choices that narrow the run list: verdict groups, roles, a date range and a text match.
_Avoid_: search (that is for log lines), query

**Log search**:
Finding text inside one run's progress log and stepping between the matches.
_Avoid_: filter (that narrows runs), find
