"""Sitemap loading + the sitemap gap report.

The gap report answers the only question that turns crawl logs into a to-do
list: which URLs that you publish in your sitemap have never been fetched by
any AI crawler?
"""

from __future__ import annotations

import gzip
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "aeo-crawl-radar/0.1 (+https://github.com/skynetlabs/aeo-crawl-radar)"
_SM_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _read_source(src: str, timeout: int = 20) -> bytes:
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = resp.read()
    else:
        data = Path(src).read_bytes()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap_bytes(data: bytes, base: str = "", _depth: int = 0) -> list[str]:
    """Parse a sitemap or sitemapindex, following nested sitemaps once fetched."""
    root = ET.fromstring(data)
    kind = _localname(root.tag)
    urls: list[str] = []
    if kind == "sitemapindex":
        for sm in root:
            loc = sm.find(f"{_SM_NS}loc")
            if loc is None:
                loc = next((c for c in sm if _localname(c.tag) == "loc"), None)
            if loc is not None and loc.text and _depth < 3:
                child = loc.text.strip()
                try:
                    urls.extend(parse_sitemap_bytes(_read_source(child), child, _depth + 1))
                except Exception:  # a broken child sitemap must not kill the run
                    continue
        return urls
    for url in root:
        loc = next((c for c in url if _localname(c.tag) == "loc"), None)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
    return urls


def load_sitemap(src: str) -> list[str]:
    """Load a sitemap from a URL or a local file path. Returns absolute URLs."""
    return parse_sitemap_bytes(_read_source(src), src)


def url_to_path(url: str) -> str:
    """Normalise a sitemap URL to the path form that appears in access logs."""
    if url.startswith(("http://", "https://")):
        parts = urllib.parse.urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path = path + "?" + parts.query
    else:
        path = url if url.startswith("/") else "/" + url
    return path


def normalise_path(path: str, ignore_query: bool = True) -> str:
    """Log-side normalisation: optional query strip, trailing-slash collapse."""
    if ignore_query and "?" in path:
        path = path.split("?", 1)[0]
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path or "/"


@dataclass
class GapReport:
    total_urls: int = 0
    crawled: list[tuple[str, list[str]]] = field(default_factory=list)
    never_crawled: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        if not self.total_urls:
            return 0.0
        return len(self.crawled) / self.total_urls * 100.0


def gap_report(sitemap_urls, path_bot_map: dict, ignore_query: bool = True) -> GapReport:
    """Compare sitemap URLs against the set of paths AI bots actually fetched."""
    crawled_norm: dict[str, set[str]] = {}
    for p, bots in path_bot_map.items():
        crawled_norm.setdefault(normalise_path(p, ignore_query), set()).update(bots)

    rep = GapReport()
    seen: set[str] = set()
    for url in sitemap_urls:
        key = normalise_path(url_to_path(url), ignore_query)
        if key in seen:
            continue
        seen.add(key)
        rep.total_urls += 1
        bots = crawled_norm.get(key)
        if bots:
            rep.crawled.append((url, sorted(bots)))
        else:
            rep.never_crawled.append(url)
    return rep
