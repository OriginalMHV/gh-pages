import tempfile
import unittest
from pathlib import Path

import check_site as cs

GOOD = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<meta http-equiv="Content-Security-Policy" content="%s">'
    "<title>t</title></head><body><h1>x</h1>"
    '<a href="#x">x</a><span id="x"></span>%%s</body></html>'
) % cs.EXPECTED_CSP


class CheckPageTest(unittest.TestCase):
    def run_page(self, body, name="index.html", html=None):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "images").mkdir()
            (site / "images" / "a.png").write_bytes(b"x")
            return cs.check_page(site, name, html if html is not None else GOOD % body)

    def messages(self, body, **kw):
        return " | ".join(self.run_page(body, **kw))

    def test_clean_page_only_reports_latest_markers(self):
        self.assertNotIn("style attribute", self.messages(""))

    def test_style_attribute_is_found(self):
        self.assertIn("style attribute", self.messages('<p style="color:red">a</p>'))

    def test_style_attribute_on_svg_is_found(self):
        self.assertIn("style attribute", self.messages('<svg><circle style="fill:red"/></svg>'))

    def test_inline_script_is_found_but_json_ld_is_allowed(self):
        self.assertIn("inline script", self.messages("<script>alert(1)</script>"))
        self.assertNotIn("inline script", self.messages('<script type="application/ld+json">{}</script>'))

    def test_event_handler_is_found(self):
        self.assertIn("event handler", self.messages('<button onclick="x()">a</button>'))

    def test_csp_mismatch_is_found(self):
        html = GOOD.replace("object-src 'none'", "object-src 'self'") % ""
        self.assertIn("CSP meta differs", self.messages("", html=html))
        html = (GOOD % "").replace('<meta http-equiv="Content-Security-Policy" content="%s">' % cs.EXPECTED_CSP, "")
        self.assertIn("exactly one CSP", self.messages("", html=html))

    def test_broken_anchor_is_found(self):
        self.assertIn("broken in-page link #nope", self.messages('<a href="#nope">a</a>'))

    def test_img_needs_alt_width_and_height(self):
        out = self.messages('<img src="images/a.png" width="1" height="1">')
        self.assertIn("img without alt", out)
        out = self.messages('<img src="images/a.png" alt="">')
        self.assertIn("img without width or height", out)
        out = self.messages('<img src="images/a.png" alt="" width="1" height="1">')
        self.assertNotIn("img without", out)

    def test_missing_local_file_is_found(self):
        self.assertIn("does not exist", self.messages('<img src="images/none.png" alt="" width="1" height="1">'))
        self.assertIn("does not exist", self.messages('<link rel="stylesheet" href="style.css">'))

    def test_forbidden_strings_are_found(self):
        for word in ("fonts.googleapis", "mailto:", "Recall", "Pulse"):
            self.assertIn("forbidden string", self.messages("<p>%s</p>" % word), word)

    def test_invalid_json_ld_is_found(self):
        self.assertIn("invalid JSON-LD", self.messages('<script type="application/ld+json">{nope</script>'))

    def test_latest_markers_are_validated(self):
        good = (
            '<!-- latest:OriginalMHV/Ward --><a class="x" href="https://github.com/OriginalMHV/Ward/releases/tag/v1.0.0">'
            "v1.0.0 · latest · 1 Jan 2026</a><!-- /latest -->"
        )
        self.assertNotIn("malformed", self.messages(good))
        self.assertIn("malformed", self.messages(good.replace("<!-- /latest -->", "")))
        self.assertIn("wrong shape", self.messages(good.replace("v1.0.0 ·", "v1.0.0 –")))
        self.assertIn("not a release URL", self.messages(good.replace("github.com/OriginalMHV/Ward/releases", "evil.example/x")))

    def test_404_needs_absolute_paths(self):
        out = self.messages('<link rel="icon" href="images/a.png">', name="404.html")
        self.assertIn("absolute path", out)
        out = self.messages('<link rel="icon" href="/images/a.png">', name="404.html")
        self.assertNotIn("absolute path", out)


if __name__ == "__main__":
    unittest.main()
