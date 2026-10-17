"""The page file (hermes_dev_watch/static/index.html) as text: dark terminal theme, no light theme, fonts wired.

    python -m unittest tests.test_page -v
"""
import pathlib, unittest

STATIC = pathlib.Path(__file__).resolve().parent.parent / "hermes_dev_watch" / "static"


class TestTerminalTheme(unittest.TestCase):
    def test_dark_terminal_page(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("prefers-color-scheme", html)
        self.assertIn("url(fonts/JetBrainsMono-Regular.woff2)", html)
        self.assertIn("url(fonts/JetBrainsMono-Bold.woff2)", html)
        self.assertIn("#0b0c0f", html)
        self.assertIn("S.version", html)
        self.assertIn("<fieldset", html)

    def test_header_fits_narrow_windows(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn("#proj{max-width:240px;text-overflow:ellipsis", html)
        self.assertIn("#ghbtn{flex-shrink:0", html)
        self.assertIn("#upd{flex-shrink:0", html)
        self.assertIn("@media (max-width:1399px){#stats .sl{display:none}", html)
        self.assertIn("@media (max-width:1299px){#upd .long{display:none}#upd .short{display:inline}#stats .lp{display:none}", html)
        self.assertIn("$('stats').title=", html)

    def test_log_times_never_wrap_and_github_icon_centered(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn(".l .ts{color:var(--dim);width:56px;flex:none;text-align:right;white-space:nowrap}", html)
        self.assertIn(".tile .l .ts{width:56px}", html)
        self.assertIn("#ghbtn{display:flex;align-items:center;align-self:center;", html)

    def test_project_picker_keeps_a_floor(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertIn(".pj{min-width:90px;", html)
        self.assertIn("#proj{max-width:240px;text-overflow:ellipsis;min-width:90px;", html)

    def test_header_is_one_line_with_short_forms(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("header{display:flex;flex-wrap", html)
        self.assertIn("#stats{flex-shrink:0", html)
        self.assertIn("@media (max-width:1299px){#upd .long{display:none}#upd .short{display:inline}", html)
        self.assertIn("@media (max-width:1099px){.brand .full{display:none}", html)
        self.assertIn('class="brand" title=', html)
        self.assertIn("v0.4.0: git pull".replace("v0.4.0", "${esc(r.latest)}"), html)

    def test_stats_column_has_by_role_and_heatmap(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for s in ("▤</span>by role", "pass rate per role, last 30 days", "no runs in 30 days", "▦</span>activity",
                  "runs per day, last 20 weeks", "#1a1d23", "#4a3d1e", "#7a6128", "#b48a34", "#e8b44c",
                  "$('ovrole')", "$('ovheat')", "p.stats"):
            self.assertIn(s, html)

    def test_key_bar_and_shortcuts(self):
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        for s in ("<footer", "<kbd>j/↓</kbd>next run", "<kbd>k/↑</kbd>prev run", "<kbd>l</kbd>live",
                  "<kbd>/</kbd>search", "<kbd>,</kbd>settings", "<kbd>esc</kbd>back",
                  "document.addEventListener('keydown'", "footer kbd{"):
            self.assertIn(s, html)


if __name__ == "__main__":
    unittest.main()
