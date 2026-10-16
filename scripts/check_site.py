#!/usr/bin/env python3
"""Static checks for the site. Standard library only. Run from anywhere:

    python3 scripts/check_site.py [site_dir]

Exit code 0 means every check passed. Exit code 1 lists each failure.
"""
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

EXPECTED_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self' https://api.open-meteo.com; base-uri 'none'; "
    "form-action 'none'; object-src 'none'"
)
FORBIDDEN = ("fonts.googleapis", "mailto:", "Recall", "Pulse")
PAGES = ("index.html", "404.html")
SITE_ORIGIN = "https://michaelhv.no"
LATEST_REPOS = ("OriginalMHV/Ward", "OriginalMHV/minimenta")
LATEST_TEXT = re.compile(
    r"^v[0-9A-Za-z.+-]+ \u00b7 latest \u00b7 \d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}$"
)
LATEST_BLOCK = re.compile(r"<!-- latest:(?P<repo>\S+) -->(?P<body>.*?)<!-- /latest -->", re.S)
JSONLD_KEYS = ("name", "jobTitle", "worksFor", "homeLocation", "url", "sameAs")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.style_attrs = 0
        self.event_attrs = []
        self.scripts = []
        self.refs = []
        self.hash_links = []
        self.hash_refs = []
        self.imgs = []
        self.csp = []
        self.h1 = 0
        self.lang = None
        self.title = ""
        self._in_title = False
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        for name in a:
            if name == "style":
                self.style_attrs += 1
            if name.startswith("on"):
                self.event_attrs.append("%s %s=" % (tag, name))
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.h1 += 1
        elif tag == "script":
            self._script = [a, ""]
            if "src" in a:
                self.refs.append(("script src", a["src"]))
        elif tag == "meta":
            if a.get("http-equiv", "").lower() == "content-security-policy":
                self.csp.append(a.get("content", ""))
            if a.get("property") == "og:image" and a.get("content"):
                self.refs.append(("og:image", a["content"]))
        elif tag == "link":
            if a.get("href") and a.get("rel") != "canonical":
                self.refs.append(("link %s" % a.get("rel", ""), a["href"]))
        elif tag == "img":
            self.imgs.append(a)
            if a.get("src"):
                self.refs.append(("img src", a["src"]))
            for candidate in a.get("srcset", "").split(","):
                candidate = candidate.strip()
                if candidate:
                    self.refs.append(("img srcset", candidate.split()[0]))
        elif tag == "a":
            href = a.get("href", "")
            if href.startswith("#"):
                self.hash_links.append(href)
            elif href:
                self.refs.append(("a href", href))
        elif tag in ("use", "image"):
            href = a.get("href", a.get("xlink:href", ""))
            if href.startswith("#"):
                self.hash_refs.append(("use", href[1:]))
        for attr in ("aria-labelledby", "aria-controls", "aria-describedby"):
            for ident in a.get(attr, "").split():
                self.hash_refs.append((attr, ident))
        clip = a.get("clip-path", "")
        match = re.fullmatch(r"url\(#([^)]+)\)", clip)
        if match:
            self.hash_refs.append(("clip-path", match.group(1)))

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._script is not None:
            self.scripts.append(tuple(self._script))
            self._script = None

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._script is not None:
            self._script[1] += data


def is_local(url):
    parts = urlsplit(url)
    return not parts.scheme and not url.startswith("//")


def resolve(site, page_name, url):
    """Return the file that a reference points to, or None when it is not a local file."""
    parts = urlsplit(url)
    if parts.scheme in ("http", "https"):
        if "%s://%s" % (parts.scheme, parts.netloc) != SITE_ORIGIN:
            return None
        path = parts.path
    elif parts.scheme or url.startswith("//"):
        return None
    else:
        path = parts.path
    if path == "":
        return site / page_name
    path = unquote(path)
    if path.startswith("/"):
        target = site / path.lstrip("/")
    else:
        target = site / Path(page_name).parent / path
    if target.is_dir() or path.endswith("/"):
        target = target / "index.html"
    return target


def check_page(site, name, text=None):
    errors = []
    if text is None:
        text = (site / name).read_text(encoding="utf-8")
    page = Page()
    page.feed(text)
    page.close()

    def err(message):
        errors.append("%s: %s" % (name, message))

    if page.style_attrs:
        err("%d style attribute(s). The CSP blocks them" % page.style_attrs)
    for item in page.event_attrs:
        err("inline event handler (%s)" % item)
    for attrs, body in page.scripts:
        if "src" in attrs:
            if not is_local(attrs["src"]):
                err("external script %s" % attrs["src"])
            continue
        if attrs.get("type") != "application/ld+json":
            err("inline script that is not application/ld+json")
    if len(page.csp) != 1:
        err("expected exactly one CSP meta, found %d" % len(page.csp))
    elif page.csp[0] != EXPECTED_CSP:
        err("CSP meta differs from the required policy")
    if page.h1 != 1:
        err("expected one h1, found %d" % page.h1)
    if not page.lang:
        err("html element has no lang")
    if not page.title.strip():
        err("empty title")
    seen = set()
    for ident in page.ids:
        if ident in seen:
            err("duplicate id %s" % ident)
        seen.add(ident)
    for link in page.hash_links:
        if link != "#" and link[1:] not in seen:
            err("broken in-page link %s" % link)
    for kind, ident in page.hash_refs:
        if ident not in seen:
            err("%s points to a missing id %s" % (kind, ident))
    for img in page.imgs:
        label = img.get("src", "?")
        if "alt" not in img:
            err("img without alt: %s" % label)
        if not img.get("width") or not img.get("height"):
            err("img without width or height: %s" % label)
    for kind, url in page.refs:
        if name == "404.html" and is_local(url) and url and not url.startswith("/"):
            err("%s %s must be an absolute path on the 404 page" % (kind, url))
        target = resolve(site, name, url)
        if target is not None and not target.is_file():
            err("%s %s does not exist" % (kind, url))
        if kind in ("script src", "link stylesheet") and not is_local(url):
            err("external %s %s" % (kind, url))
    lowered = text.lower()
    for word in FORBIDDEN:
        found = word.lower() in lowered if word.islower() else word in text
        if found:
            err("forbidden string %r" % word)
    for attrs, body in page.scripts:
        if attrs.get("type") == "application/ld+json":
            try:
                data = json.loads(body)
            except ValueError as exc:
                err("invalid JSON-LD: %s" % exc)
                continue
            if data.get("@context") != "https://schema.org" or data.get("@type") != "Person":
                err("JSON-LD must be a schema.org Person")
            for key in JSONLD_KEYS:
                if not data.get(key):
                    err("JSON-LD is missing %s" % key)
    errors.extend(check_latest(name, text))
    return errors


def check_latest(name, text):
    errors = []
    starts = len(re.findall(r"<!-- latest:", text))
    ends = len(re.findall(r"<!-- /latest -->", text))
    blocks = list(LATEST_BLOCK.finditer(text))
    if starts != ends or starts != len(blocks):
        errors.append("%s: malformed latest markers (%d open, %d close, %d pairs)" % (name, starts, ends, len(blocks)))
    found = []
    for block in blocks:
        repo, body = block.group("repo"), block.group("body")
        found.append(repo)
        if not re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", repo):
            errors.append("%s: bad latest marker repo %r" % (name, repo))
            continue
        anchor = re.fullmatch(r'<a class="([^"]*)" href="([^"]*)">([^<]*)</a>', body)
        if not anchor:
            errors.append("%s: latest block for %s must hold exactly one link" % (name, repo))
            continue
        prefix = "https://github.com/%s/releases/tag/" % repo
        if not anchor.group(2).startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9._+-]+", anchor.group(2)[len(prefix):]):
            errors.append("%s: latest link for %s is not a release URL" % (name, repo))
        if not LATEST_TEXT.match(anchor.group(3)):
            errors.append("%s: latest label for %s has the wrong shape: %r" % (name, repo, anchor.group(3)))
    if name == "index.html":
        for repo in LATEST_REPOS:
            if repo not in found:
                errors.append("%s: missing latest marker for %s" % (name, repo))
    return errors


def check_css(site):
    errors = []
    for css in sorted(site.glob("*.css")):
        text = css.read_text(encoding="utf-8")
        if "@import" in text:
            errors.append("%s: @import is not allowed" % css.name)
        for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", text):
            if url.startswith("data:"):
                continue
            if not is_local(url):
                errors.append("%s: external url %s" % (css.name, url))
                continue
            target = css.parent / urlsplit(url).path
            if not target.is_file():
                errors.append("%s: url(%s) does not exist" % (css.name, url))
    return errors


def check_site(site):
    site = Path(site)
    errors = []
    for name in PAGES:
        if not (site / name).is_file():
            errors.append("missing %s" % name)
            continue
        errors.extend(check_page(site, name))
    errors.extend(check_css(site))
    cname = site / "CNAME"
    if not cname.is_file() or not cname.read_text(encoding="utf-8").strip():
        errors.append("CNAME is missing or empty")
    for extra in ("robots.txt", "sitemap.xml", "favicon.svg", "apple-touch-icon.png"):
        if not (site / extra).is_file():
            errors.append("missing %s" % extra)
    return errors


def main(argv):
    default = Path(__file__).resolve().parent.parent / "site"
    site = Path(argv[1]) if len(argv) > 1 else default
    errors = check_site(site)
    for line in errors:
        print("FAIL " + line)
    if errors:
        print("%d problem(s) found" % len(errors))
        return 1
    print("check_site: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
