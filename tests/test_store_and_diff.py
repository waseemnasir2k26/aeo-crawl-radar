from datetime import datetime, timedelta, timezone

from aeo_crawl_radar import report
from aeo_crawl_radar.cli import ingest, parse_when
from aeo_crawl_radar.store import Store

END = datetime(2026, 8, 31, 23, 0, tzinfo=timezone.utc)


def _load(db_path, taxonomy, log):
    store = Store(db_path)
    stats, formats = ingest([log], store, taxonomy)
    return store, stats, formats


def test_ingest_stores_only_crawler_hits(db_path, taxonomy, nginx_log):
    store, stats, formats = _load(db_path, taxonomy, nginx_log)
    assert formats == ["nginx"]
    assert stats.parsed == 651
    assert stats.bot_hits == 491          # 388 AI + 103 reference
    assert stats.inserted == 491
    assert store.count() == 491
    assert store.count(ai_only=True) == 388
    store.close()


def test_second_ingest_is_idempotent(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    stats2, _ = ingest([nginx_log], store, taxonomy)
    assert stats2.inserted == 0
    assert stats2.duplicates == 491
    assert store.count() == 491
    store.close()


def test_data_persists_across_connections(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    store.close()
    reopened = Store(db_path)
    assert reopened.count() == 491
    assert reopened.bot_summary()[0]["hits"] > 0
    reopened.close()


def test_same_traffic_from_another_format_dedupes(db_path, taxonomy, fixtures):
    store, _, _ = _load(db_path, taxonomy, fixtures / "access.nginx.log")
    before = store.count()
    stats, _ = ingest([fixtures / "cloudflare.logpush.jsonl"], store, taxonomy)
    assert store.count() == before
    assert stats.inserted == 0
    store.close()


def test_bot_summary_shape(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    rows = {r["bot"]: r for r in store.bot_summary()}
    assert "Googlebot" not in rows          # ai_only default
    gpt = rows["GPTBot"]
    assert gpt["hits"] == 86
    assert gpt["vendor"] == "OpenAI" and gpt["purpose"] == "training"
    assert gpt["first_seen"] < gpt["last_seen"]
    assert gpt["paths"] >= 5
    assert gpt["bytes"] > 0
    store.close()


def test_window_filtering(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    lo, hi = store.time_bounds()
    mid = lo + (hi - lo) / 2
    early = store.count(until=mid, ai_only=True)
    late = store.count(since=mid, ai_only=True)
    assert early + late == store.count(ai_only=True)
    assert early > 0 and late > 0
    store.close()


def test_status_and_paths(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    statuses = {r["status"]: r["hits"] for r in store.status_breakdown()}
    assert statuses[200] > 0
    assert 404 in statuses
    top = store.top_paths(limit=3)
    assert len(top) == 3
    assert top[0]["hits"] >= top[-1]["hits"]
    per_bot = store.top_paths(bot="ClaudeBot", limit=5)
    assert sum(p["hits"] for p in per_bot) <= 61
    store.close()


def test_diff_two_weeks(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    d = report.build_diff(store, weeks=2, until=END)
    rows = {r["bot"]: r for r in d["bots"]}

    # CCBot only ever crawls in the recent window -> new
    assert rows["CCBot"]["state"] == "new"
    assert rows["CCBot"]["previous"] == 0 and rows["CCBot"]["current"] == 12

    # Bytespider tails off hard
    assert rows["Bytespider"]["delta"] < 0

    # GPTBot grew
    assert rows["GPTBot"]["delta"] > 0
    assert rows["GPTBot"]["pct"] is not None

    assert d["current_hits"] > d["previous_hits"]
    assert d["current_window"][1] == END.isoformat()
    store.close()


def test_diff_render_is_text(db_path, taxonomy, nginx_log):
    store, _, _ = _load(db_path, taxonomy, nginx_log)
    text = report.render_diff(report.build_diff(store, weeks=2, until=END))
    assert "CRAWL DIFF" in text
    assert "CCBot" in text
    store.close()


def test_parse_when_relative_and_iso():
    now = datetime.now(timezone.utc)
    assert parse_when(None) is None
    assert abs((now - parse_when("7d")) - timedelta(days=7)).total_seconds() < 5
    assert abs((now - parse_when("12h")) - timedelta(hours=12)).total_seconds() < 5
    assert abs((now - parse_when("2w")) - timedelta(weeks=2)).total_seconds() < 5
    assert parse_when("2026-08-01") == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert parse_when("2026-08-01T06:30:00Z") == datetime(
        2026, 8, 1, 6, 30, tzinfo=timezone.utc
    )
