import pytest

from aeo_crawl_radar.cli import ingest
from aeo_crawl_radar.sitemap import (
    gap_report,
    load_sitemap,
    normalise_path,
    parse_sitemap_bytes,
    url_to_path,
)
from aeo_crawl_radar.store import Store

EXPECTED_NEVER = {
    "/blog/schema-markup-for-answers",
    "/blog/entity-seo-primer",
    "/blog/measuring-ai-referrals",
    "/services/aeo-retainer",
    "/services/log-analysis",
    "/case-studies/regional-retailer",
    "/case-studies/b2b-saas",
    "/careers",
    "/legal/privacy",
    "/legal/terms",
}


def test_load_local_sitemap(fixtures):
    urls = load_sitemap(str(fixtures / "sitemap.xml"))
    assert len(urls) == 22
    assert all(u.startswith("https://example-shop.test/") for u in urls)


def test_url_to_path_and_normalise():
    assert url_to_path("https://a.test/blog/x") == "/blog/x"
    assert url_to_path("https://a.test") == "/"
    assert url_to_path("/already/a/path") == "/already/a/path"
    assert url_to_path("https://a.test/p?ref=1") == "/p?ref=1"
    assert normalise_path("/p?ref=1") == "/p"
    assert normalise_path("/blog/x/") == "/blog/x"
    assert normalise_path("/") == "/"


def test_sitemapindex_is_followed_or_ignored_safely():
    xml = (
        b'<?xml version="1.0"?>'
        b'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        b"<sitemap><loc>https://unreachable.invalid/sitemap-1.xml</loc></sitemap>"
        b"</sitemapindex>"
    )
    # A child sitemap that cannot be fetched must not raise.
    assert parse_sitemap_bytes(xml) == []


def test_gap_report_finds_never_crawled_urls(db_path, taxonomy, fixtures):
    store = Store(db_path)
    ingest([fixtures / "access.nginx.log"], store, taxonomy)
    rep = gap_report(
        load_sitemap(str(fixtures / "sitemap.xml")), store.path_bot_map()
    )
    never = {u.replace("https://example-shop.test", "") for u in rep.never_crawled}
    assert never == EXPECTED_NEVER
    assert rep.total_urls == 22
    assert len(rep.crawled) == 12
    assert round(rep.coverage, 1) == pytest.approx(54.5, abs=0.1)
    store.close()


def test_gap_report_names_the_bots_that_fetched_each_url(db_path, taxonomy, fixtures):
    store = Store(db_path)
    ingest([fixtures / "access.nginx.log"], store, taxonomy)
    rep = gap_report(
        load_sitemap(str(fixtures / "sitemap.xml")), store.path_bot_map()
    )
    by_url = dict(rep.crawled)
    home = by_url["https://example-shop.test/"]
    assert "GPTBot" in home
    assert "Googlebot" not in home           # AI bots only
    store.close()


def test_gap_report_shrinks_with_a_narrow_window(db_path, taxonomy, fixtures):
    store = Store(db_path)
    ingest([fixtures / "access.nginx.log"], store, taxonomy)
    lo, hi = store.time_bounds()
    urls = load_sitemap(str(fixtures / "sitemap.xml"))
    full = gap_report(urls, store.path_bot_map())
    narrow = gap_report(urls, store.path_bot_map(since=hi - (hi - lo) / 8))
    assert len(narrow.never_crawled) >= len(full.never_crawled)
    store.close()


def test_gap_report_with_no_data_marks_everything_uncrawled(fixtures):
    rep = gap_report(load_sitemap(str(fixtures / "sitemap.xml")), {})
    assert len(rep.never_crawled) == 22
    assert rep.coverage == 0.0


def test_query_strings_do_not_hide_a_crawl():
    rep = gap_report(["https://a.test/page"], {"/page?utm_source=x": {"GPTBot"}})
    assert rep.never_crawled == []
    assert rep.crawled == [("https://a.test/page", ["GPTBot"])]
