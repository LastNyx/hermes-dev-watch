# Dev notes

Facts that dev workers had to work out. Read before changing the reader, the page or the tests.

## Tests

- Test command: `python -m unittest discover -s tests -v`. `tests/test_contract.py` puts the repo root on `sys.path`
  itself and imports `hermes_dev_watch.core`; pywebview is not installed where tests run, so `app.py` is untested.
- Kit-sample tests read `HDW_KIT_DIR` in `setUpClass`, not at import, so `python tests/test_contract.py <kit>` can set
  it before `unittest.main`. Without it they skip.
- To test the 200-run cap, patch `core.MAX_RUNS` with `mock.patch.object`; to test chunked reads, set `core.CHUNK`
  in a `try`/`finally`.

## Reader (`core.py`)

- `project_state` gets its runs from `filter_runs`. `total` is the filtered count, `run_count` counts all runs, and
  `live_runs`, `roles` and `today` ignore the filter.
- `project_state(..., open_run=<run id>)` adds `"open"`: that run, fresh and unfiltered. The page sends
  `{project, run}` through `API.state` while a run is open in the detail view, and keeps no copy of its own.
- `progress()` offsets are byte positions in the file; the text is decoded, then `\r\n` becomes `\n` (the kit writes
  `\r\n` on Windows).
- `search_log` numbers lines like the page: `\r\n` to `\n`, split on `\n`, drop blank and whitespace-only lines. The
  page builds one line element per such line. `Api.search` mirrors `Api.progress` (known projects only).

## Page (`static/index.html`)

- The run filter is `runFilter` (store key `runfilter`); `filt` is the separate line-kind filter of a run's log. The
  page polls `API.state(runFilter)` once a second.
- The detail view builds its tools row (`#fb` line-kind buttons, `#ls` search box, `#lc` count, follow) once per run;
  only `#dh` and `#fb` re-render each second, so the search box keeps focus. Search state is `sr`; `size` is the file
  size from the last `pull`. `visHits()` relies on `offsetParent`, so the `#fs` kind-filter style must apply first;
  `keepCur()` re-picks the current match after a line-kind click.
