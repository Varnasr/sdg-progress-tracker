#!/usr/bin/env python3
"""Static checks for this single-page data explorer. No dependencies.

The repository had no CI, so nothing held the page to its own security policy.

The specific thing this exists for: the Content-Security-Policy is declared
**twice**, as a `<meta http-equiv>` in index.html and as a header in
netlify.toml. A browser enforces the intersection of the two, so the tighter one
governs and the looser one is invisible. They had drifted: the header was copied
verbatim from the Experiments repository, which hosts many tools, and allowed 17
origins this site never touches. Nothing broke, and nothing would have, until
someone deleted the meta tag believing the header covered it and silently widened
the policy instead.

A CSP that is too tight fails silently too: the script simply does not load, the
chart does not draw, and only the browser console says why.

Run:  python3 scripts/check.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
TOML = (ROOT / "netlify.toml").read_text(encoding="utf-8")

failures = []


def check(name, fn):
    try:
        note = fn()
        print(f"  ok    {name}" + (f" ({note})" if note else ""))
    except AssertionError as e:
        failures.append(name)
        print(f"  FAIL  {name}\n        {e}")


def parse_csp(text):
    out = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        name, *values = part.split()
        out[name] = set(values)
    return out


def origins(urls):
    got = set()
    for u in urls:
        m = re.match(r"(https?://[^/\s]+)", u)
        if m:
            got.add(m.group(1))
    return got


meta_m = re.search(r'http-equiv="Content-Security-Policy"\s+content="([^"]+)"', HTML)
head_m = re.search(r'Content-Security-Policy\s*=\s*"([^"]+)"', TOML)


def _both_present():
    assert meta_m, "index.html has no Content-Security-Policy meta tag"
    assert head_m, "netlify.toml sets no Content-Security-Policy header"
check("the page and the deploy config both declare a CSP", _both_present)

meta = parse_csp(meta_m.group(1)) if meta_m else {}
head = parse_csp(head_m.group(1)) if head_m else {}

# Directives the header adds as hardening; the meta tag has no reason to repeat
# them because they cannot be relaxed by their absence.
HEADER_ONLY = {"object-src", "worker-src", "media-src"}


def _agree():
    shared = (set(meta) | set(head)) - HEADER_ONLY
    diffs = []
    for d in sorted(shared):
        a, b = meta.get(d, set()), head.get(d, set())
        if a != b:
            only_head = sorted(b - a)
            only_meta = sorted(a - b)
            bits = []
            if only_head:
                bits.append(f"header allows {only_head}")
            if only_meta:
                bits.append(f"meta allows {only_meta}")
            diffs.append(f"{d}: " + "; ".join(bits))
    assert not diffs, (
        "the two policies disagree, so the tighter one silently governs:\n        "
        + "\n        ".join(diffs)
    )
    return f"{len(shared)} directives identical in both"
check("the meta CSP and the header CSP say the same thing", _agree)


def _covers_usage():
    """Anything the page loads must be allowed, or it fails with no visible error."""
    checks = [
        ("script-src", origins(re.findall(r'<script[^>]+src="([^"]+)"', HTML))),
        # Only real stylesheets. A Google Fonts <link> pulls CSS from
        # fonts.googleapis.com (style-src) and the font files from
        # fonts.gstatic.com (font-src); lumping them together reports a
        # violation that does not exist.
        ("style-src", origins(
            re.findall(r'<link[^>]+rel="stylesheet"[^>]*href="([^"]+)"', HTML)
            + re.findall(r'<link[^>]+href="([^"]+)"[^>]*rel="stylesheet"', HTML))),
        ("font-src", origins(
            re.findall(r'<link[^>]+href="(https://fonts\.gstatic\.com[^"]*)"', HTML))),
        ("img-src", origins(re.findall(r'<img[^>]+src="([^"]+)"', HTML))),
    ]
    blocked = []
    for directive, used in checks:
        allowed = meta.get(directive, set()) | meta.get("default-src", set())
        for origin in used:
            if origin not in allowed:
                blocked.append(f"{directive}: {origin}")
    assert not blocked, "loaded but not allowed by the CSP: " + ", ".join(blocked)
    return "every subresource origin in the page is allowed"
check("the CSP allows everything the page actually loads", _covers_usage)


def _fetch_targets_allowed():
    """Iconify fetches its icon data at runtime, which connect-src governs."""
    conn = meta.get("connect-src", set()) | meta.get("default-src", set())
    if "<iconify-icon" in HTML or "iconify-icon.min.js" in HTML:
        for needed in ("https://api.iconify.design", "https://api.simplesvg.com",
                       "https://api.unisvg.com"):
            assert needed in conn, (
                f"the page uses iconify-icon, which fetches icon data at runtime, "
                f"but connect-src does not allow {needed}. Icons render as empty "
                f"boxes with only a console message."
            )
    return "iconify icon-data origins allowed" if "<iconify-icon" in HTML else None
check("runtime fetch targets are allowed", _fetch_targets_allowed)


def _no_hardcoded_latest_year():
    """A pinned year makes the page quietly stale a year after it is written."""
    if "new Date().getFullYear()" in HTML:
        return "the latest year is derived from the clock, not pinned"
    pinned = re.findall(r"(?:LATEST|YEAR_MAX|CURRENT_YEAR)\s*=\s*(20\d\d)", HTML)
    assert not pinned, (
        f"a year is hardcoded ({', '.join(pinned)}). The page will show stale data "
        f"from the next release onwards without anything failing."
    )
check("no hardcoded 'latest year'", _no_hardcoded_latest_year)


def _page_basics():
    assert re.search(r"<html[^>]+lang=", HTML), "no lang attribute on <html>"
    assert re.search(r'<meta[^>]+name=["\']?viewport', HTML, re.I), (
        "no viewport meta; a phone lays the page out at desktop width")
    assert re.search(r"<title>[^<]+</title>", HTML), "no title"
    m = re.search(r"<title>([^<]+)</title>", HTML)
    return m.group(1)[:48]
check("page basics", _page_basics)


def _inline_handlers_are_permitted():
    """Inline handlers are fine here, and only here, because script-src carries
    'unsafe-inline'. If that is ever tightened to a nonce or hash, every one of
    them stops firing with no error on the page."""
    found = re.findall(r"\son(?:click|change|load|submit|error)\s*=", HTML)
    if not found:
        return "none used"
    allowed = "'unsafe-inline'" in meta.get("script-src", set())
    assert allowed, (
        f"{len(found)} inline event handlers, but script-src no longer allows "
        f"'unsafe-inline', so none of them fire. Move them to addEventListener.")
    return f"{len(found)} used, and script-src still allows 'unsafe-inline'"
check("inline handlers match what the CSP permits", _inline_handlers_are_permitted)


print()
if failures:
    print(f"FAIL - {len(failures)} check(s) failed")
    sys.exit(1)
print("PASS - all checks passed")
