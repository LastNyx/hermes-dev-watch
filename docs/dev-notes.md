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

## Restyle (0.4.0)

- `core.run_stats(runs, now)` windows: 30 days = now.date and 29 before; 140 days = now.date and 139 before (2026-10-16 -> first day 20260530).
- `tests/test_page.py` reads `static/index.html` as text (no browser, no webview); `app.py` imports webview so it can't be imported in tests.
- The page's `#main` is the middle panel body; the panel title is `#mleg` via `setLeg()`; the right column body is `#ov`.
- Header `#stats` is built in `renderTop()` with `.sl` (long words), `.ss` (✓/✗ short marks) and `.lp` (list $) spans; CSS `@media` at 1399px and 1299px hides them, and the full text goes in `#stats` `title`.
- Header update banner `#upd` holds `.long`/`.short` spans (swapped at 1299px); brand has `.full` and project label `.pl`, both hidden at 1099px; the header never wraps (no `flex-wrap`).
- Right column sections `#ovtoday`, `#ovrole`, `#ovheat` are all filled in `renderTop()` from `shown().map(p=>p.stats)`; heatmap is a CSS grid (`.hm`) with explicit grid-row/column per cell.
- Key bar is a `<footer>` of `<kbd>` chips (brackets come from CSS); one `document` keydown handler after `$('livebtn').onclick` does the shortcuts via `allRuns()`, `open()`, and the nav buttons' `onclick`.
- `blocks(f,n=12)` is the only bar helper (by-role passes 10); heatmap grid and legend cells share `#ov :is(.hm,.hl) i.lN` color rules.
- Log time column `.l .ts` (56px, nowrap) is shared by run log and `.tile .l .ts`; header uses `align-items:flex-end`, so `#ghbtn` overrides with `align-self:center`.
- Project picker CSS: wrapper `.pj` (label `.pl` + `<select id="proj">`) and `#proj` both need `min-width:90px`; `.pj` has `overflow:hidden`, so a 0 floor on either squeezes the select to nothing.
