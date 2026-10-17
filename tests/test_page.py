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


if __name__ == "__main__":
    unittest.main()
