import io
import json
import os
import tempfile
import unittest
import urllib.error

import update_latest as ul

PAGE = (
    "<p>before</p>\n"
    '<!-- latest:OriginalMHV/Ward --><a class="d02-a d02-rel latest" '
    'href="https://github.com/OriginalMHV/Ward/releases/tag/v0.6.2">v0.6.2 · latest · 15 Oct 2026</a><!-- /latest -->\n'
    "<p>middle</p>\n"
    '<!-- latest:OriginalMHV/minimenta --><a class="d02-a d02-rel latest" '
    'href="https://github.com/OriginalMHV/minimenta/releases/tag/v0.1.0">v0.1.0 · latest · 10 Oct 2026</a><!-- /latest -->\n'
    "<p>after</p>\n"
)


def release(repo, tag, published="2026-10-15T09:30:00Z", url=None):
    return {
        "tag_name": tag,
        "html_url": url or "https://github.com/%s/releases/tag/%s" % (repo, tag),
        "published_at": published,
    }


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class UpdateTextTest(unittest.TestCase):
    def test_normal_update_rewrites_only_between_markers(self):
        def fetch(repo):
            if repo.endswith("Ward"):
                return release(repo, "v0.7.0", "2026-11-03T08:00:00Z")
            return release(repo, "v0.1.0", "2026-10-10T08:00:00Z")

        new, warnings = ul.update_text(PAGE, fetch)
        self.assertEqual(warnings, [])
        self.assertIn(
            '<!-- latest:OriginalMHV/Ward --><a class="d02-a d02-rel latest" '
            'href="https://github.com/OriginalMHV/Ward/releases/tag/v0.7.0">v0.7.0 · latest · 3 Nov 2026</a><!-- /latest -->',
            new,
        )
        self.assertTrue(new.startswith("<p>before</p>\n"))
        self.assertIn("<p>middle</p>\n", new)
        self.assertTrue(new.endswith("<p>after</p>\n"))
        self.assertIn("v0.1.0 · latest · 10 Oct 2026", new)

    def test_unchanged_file_stays_byte_identical(self):
        def fetch(repo):
            tag, published = ("v0.6.2", "2026-10-15T01:00:00Z") if repo.endswith("Ward") else ("v0.1.0", "2026-10-10T23:59:59Z")
            return release(repo, tag, published)

        new, warnings = ul.update_text(PAGE, fetch)
        self.assertEqual(new, PAGE)
        self.assertEqual(warnings, [])

    def test_api_error_keeps_the_fallback(self):
        def fetch(repo):
            raise ul.ReleaseError("boom")

        new, warnings = ul.update_text(PAGE, fetch)
        self.assertEqual(new, PAGE)
        self.assertEqual(len(warnings), 2)

    def test_unexpected_exception_keeps_the_fallback(self):
        def fetch(repo):
            return None

        new, warnings = ul.update_text(PAGE, fetch)
        self.assertEqual(new, PAGE)
        self.assertEqual(len(warnings), 2)

    def test_hostile_tag_is_rejected(self):
        for tag in ('v1"><script>alert(1)</script>', "v1 2", "v1\nv2", "", "a" * 65, "v1<b>"):
            def fetch(repo, tag=tag):
                return {
                    "tag_name": tag,
                    "html_url": "https://github.com/%s/releases/tag/v1" % repo,
                    "published_at": "2026-10-15T09:30:00Z",
                }

            new, warnings = ul.update_text(PAGE, fetch)
            self.assertEqual(new, PAGE, tag)
            self.assertEqual(len(warnings), 2, tag)

    def test_hostile_url_is_rejected(self):
        bad_urls = [
            "https://evil.example/OriginalMHV/Ward/releases/tag/v1.0.0",
            "javascript:alert(1)",
            "https://github.com/OriginalMHV/Ward/releases/tag/v1.0.0\"onmouseover=\"x",
            "https://github.com/OriginalMHV/Ward-evil/releases/tag/v1.0.0",
            "https://github.com/OriginalMHV/Ward/releases/tag/v2.0.0",
            "https://github.com/OriginalMHV/Ward/releases/tag/v1.0.0/../../x",
            None,
        ]
        for url in bad_urls:
            def fetch(repo, url=url):
                return {"tag_name": "v1.0.0", "html_url": url, "published_at": "2026-10-15T09:30:00Z"}

            new, warnings = ul.update_text(PAGE, fetch)
            self.assertEqual(new, PAGE, url)
            self.assertTrue(warnings, url)

    def test_bad_date_is_rejected(self):
        for stamp in (None, "yesterday", "2026-13-01T00:00:00Z", "2026-10-00T00:00:00Z"):
            def fetch(repo, stamp=stamp):
                return release(repo, "v1.0.0", stamp)

            new, warnings = ul.update_text(PAGE, fetch)
            self.assertEqual(new, PAGE, stamp)

    def test_missing_markers_is_a_no_op(self):
        text = "<p>no markers here</p>"
        calls = []
        new, warnings = ul.update_text(text, lambda repo: calls.append(repo))
        self.assertEqual(new, text)
        self.assertEqual(calls, [])
        self.assertEqual(len(warnings), 1)

    def test_labels_never_depend_on_the_locale(self):
        self.assertEqual(ul.format_date("2026-03-07T10:00:00Z"), "7 Mar 2026")
        self.assertEqual(ul.format_date("2026-12-31T23:59:59Z"), "31 Dec 2026")

    def test_percent_encoded_plus_in_url_matches_the_tag(self):
        link = ul.render("OriginalMHV/Ward", release("OriginalMHV/Ward", "v1.0.0+build", url="https://github.com/OriginalMHV/Ward/releases/tag/v1.0.0%2Bbuild"))
        self.assertIn("v1.0.0+build · latest", link)


class FetchTest(unittest.TestCase):
    def test_parses_json_and_sends_the_token(self):
        seen = {}

        def opener(request, timeout):
            seen["auth"] = request.get_header("Authorization")
            seen["url"] = request.full_url
            return FakeResponse(json.dumps({"tag_name": "v1"}).encode())

        data = ul.fetch_latest("OriginalMHV/Ward", "secret", opener)
        self.assertEqual(data["tag_name"], "v1")
        self.assertEqual(seen["auth"], "Bearer secret")
        self.assertEqual(seen["url"], "https://api.github.com/repos/OriginalMHV/Ward/releases/latest")

    def test_http_error_becomes_release_error(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 403, "rate limited", {}, io.BytesIO())

        with self.assertRaises(ul.ReleaseError):
            ul.fetch_latest("OriginalMHV/Ward", None, opener)

    def test_bad_json_becomes_release_error(self):
        def opener(request, timeout):
            return FakeResponse(b"<html>not json</html>")

        with self.assertRaises(ul.ReleaseError):
            ul.fetch_latest("OriginalMHV/Ward", None, opener)


class MainTest(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_main_exits_zero_and_keeps_the_file_when_the_network_fails(self):
        path = self.write(PAGE)
        original = ul.fetch_latest
        ul.fetch_latest = lambda repo, token=None, opener=None: (_ for _ in ()).throw(ul.ReleaseError("offline"))
        try:
            self.assertEqual(ul.main(["update_latest.py", path]), 0)
        finally:
            ul.fetch_latest = original
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), PAGE)

    def test_main_updates_the_file(self):
        path = self.write(PAGE)
        original = ul.fetch_latest
        ul.fetch_latest = lambda repo, token=None, opener=None: release(repo, "v9.9.9", "2027-01-02T00:00:00Z")
        try:
            self.assertEqual(ul.main(["update_latest.py", path]), 0)
        finally:
            ul.fetch_latest = original
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("v9.9.9 · latest · 2 Jan 2027", text)

    def test_main_exits_zero_when_the_file_is_missing(self):
        self.assertEqual(ul.main(["update_latest.py", "/nonexistent/index.html"]), 0)

    def test_main_needs_one_argument(self):
        self.assertEqual(ul.main(["update_latest.py"]), 2)


if __name__ == "__main__":
    unittest.main()
