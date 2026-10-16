#!/usr/bin/env python3
"""Refresh the "latest release" labels in site/index.html. Standard library only.

    python3 scripts/update_latest.py site/index.html

Every label sits between two markers:

    <!-- latest:OWNER/REPO --><a ...>v1.2.3 &middot; latest &middot; 15 Oct 2026</a><!-- /latest -->

The script asks the GitHub API for the latest release of each repository and rewrites
only the text between the markers. On any API or parse error it keeps the committed
label, prints a warning and still exits with 0, so a deploy never fails because of it.
Set GH_TOKEN to raise the API rate limit.
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import unquote

MARKER = re.compile(
    r"(?P<open><!-- latest:(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+) -->)(?P<body>.*?)(?P<close><!-- /latest -->)",
    re.S,
)
TAG = re.compile(r"[A-Za-z0-9._+-]{1,64}")
URL_TAIL = re.compile(r"[A-Za-z0-9._+%-]+")
PUBLISHED = re.compile(r"(\d{4})-(\d{2})-(\d{2})T")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LINK_CLASS = "d02-a d02-rel latest"
API = "https://api.github.com/repos/%s/releases/latest"


class ReleaseError(Exception):
    pass


def fetch_latest(repo, token=None, opener=urllib.request.urlopen):
    """Return the parsed JSON of the latest release of repo."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "michaelhv-site-latest-labels",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(API % repo, headers=headers)
    try:
        with opener(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ReleaseError("could not read the latest release of %s: %s" % (repo, exc))


def format_date(published_at):
    match = PUBLISHED.match(published_at or "")
    if not match:
        raise ReleaseError("unexpected published_at %r" % (published_at,))
    year, month, day = (int(part) for part in match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        raise ReleaseError("unexpected published_at %r" % (published_at,))
    return "%d %s %d" % (day, MONTHS[month - 1], year)


def render(repo, release):
    """Return the new link for one repository, or raise ReleaseError."""
    if not isinstance(release, dict):
        raise ReleaseError("release is not an object")
    tag = release.get("tag_name")
    url = release.get("html_url")
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise ReleaseError("rejected tag %r" % (tag,))
    prefix = "https://github.com/%s/releases/tag/" % repo
    if not isinstance(url, str) or not url.startswith(prefix):
        raise ReleaseError("rejected release URL %r" % (url,))
    tail = url[len(prefix):]
    if not URL_TAIL.fullmatch(tail) or unquote(tail) != tag:
        raise ReleaseError("release URL does not match the tag %r" % (tag,))
    label = "%s · latest · %s" % (tag, format_date(release.get("published_at")))
    return '<a class="%s" href="%s">%s</a>' % (LINK_CLASS, html.escape(url, quote=True), html.escape(label, quote=True))


def update_text(text, fetch):
    """Return (new_text, warnings). fetch(repo) returns the release JSON or raises ReleaseError."""
    warnings = []
    if not MARKER.search(text):
        warnings.append("no latest markers found, nothing to update")
        return text, warnings

    def replace(match):
        repo = match.group("repo")
        try:
            link = render(repo, fetch(repo))
        except Exception as exc:
            warnings.append("%s: %s. Keeping the committed label" % (repo, exc))
            return match.group(0)
        return match.group("open") + link + match.group("close")

    return MARKER.sub(replace, text), warnings


def main(argv):
    if len(argv) != 2:
        print("usage: update_latest.py PATH_TO_INDEX_HTML", file=sys.stderr)
        return 2
    path = argv[1]
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        print("warning: cannot read %s: %s" % (path, exc))
        return 0
    token = os.environ.get("GH_TOKEN") or None
    new_text, warnings = update_text(text, lambda repo: fetch_latest(repo, token))
    for line in warnings:
        print("warning: " + line)
    if new_text == text:
        print("latest labels unchanged")
        return 0
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(new_text)
    print("latest labels updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
