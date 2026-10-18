"""Validates one RSS feed. Usage: check_feed.py FILE LANG BASEURL EXPECTED_LINK...
Asserts: well-formed RSS 2.0, channel language, absolute links under BASEURL, RFC 822 dates, lastBuildDate,
atom self link, plain-text descriptions, and that the item links equal EXPECTED_LINK (newest first)."""
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ATOM = "{http://www.w3.org/2005/Atom}"
path, lang, base, *expected = sys.argv[1:]
root = ET.parse(path).getroot()  # raises on malformed XML
assert root.tag == "rss" and root.get("version") == "2.0", "not RSS 2.0"
ch = root.find("channel")
assert ch is not None, "no channel"
for tag in ("title", "link", "description", "language"):
    assert (ch.findtext(tag) or "").strip(), f"channel lacks {tag}"
assert ch.findtext("language") == lang, f"channel language {ch.findtext('language')} != {lang}"
has_items = ch.find("item") is not None
lbd = ch.findtext("lastBuildDate")
if has_items:
    assert lbd, "channel lacks lastBuildDate"
    parsedate_to_datetime(lbd)
else:
    assert lbd is None, "an empty feed must omit lastBuildDate (no build-time value)"
assert ch.findtext("link").startswith(base), "channel link not under baseURL"
sl = ch.find(ATOM + "link")
assert sl is not None and sl.get("rel") == "self" and sl.get("href").startswith(base), "no atom self link"
links, dates = [], []
for it in ch.findall("item"):
    link = it.findtext("link")
    assert link and link.startswith(base), f"item link not absolute under baseURL: {link}"
    assert (it.findtext("title") or "").strip(), "item lacks title"
    d = (it.findtext("description") or "").strip()
    assert d and "<" not in d.replace("< ", ""), f"description is not plain text: {d}"
    dates.append(parsedate_to_datetime(it.findtext("pubDate")))
    assert it.findtext("guid") == link, "guid must be the permalink"
    links.append(link)
assert dates == sorted(dates, reverse=True), "items not newest first"
want = [base + e.lstrip("/") for e in expected]
assert links == want, f"items {links} != expected {want}"
if len(sys.argv) > 4:
    for it in ch.findall("item"):
        if "/writing/en-postmortem/" in it.findtext("link"):
            assert it.findtext("title") == 'Fixture "outage" & <recovery> notes', it.findtext("title")
            assert it.findtext("description") == "An invented outage, sizes < 10 units & more.", it.findtext("description")
print("feed ok:", path)
