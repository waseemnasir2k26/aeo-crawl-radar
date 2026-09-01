from datetime import timezone

import pytest

from aeo_crawl_radar.parsers import detect_format, parse_file, sniff_file

FILES = {
    "nginx": "access.nginx.log",
    "apache": "access.apache.log",
    "cloudflare": "cloudflare.logpush.jsonl",
    "vercel": "vercel.drain.jsonl",
}


@pytest.mark.parametrize("fmt,name", FILES.items())
def test_autodetect(fixtures, fmt, name):
    assert sniff_file(fixtures / name) == fmt


@pytest.mark.parametrize("fmt,name", FILES.items())
def test_every_line_parses(fixtures, fmt, name):
    res = parse_file(fixtures / name)
    assert res.fmt == fmt
    assert res.skipped == 0
    assert res.parsed == 651


def test_all_four_formats_agree(fixtures):
    """The four fixtures describe the same traffic; parsers must converge."""
    sets = {}
    for fmt, name in FILES.items():
        res = parse_file(fixtures / name)
        sets[fmt] = sorted(
            (e.ts.isoformat(), e.ip, e.method, e.path, e.status, e.bytes, e.user_agent)
            for e in res.events
        )
    base = sets["nginx"]
    for fmt, rows in sets.items():
        assert rows == base, f"{fmt} disagrees with nginx"


def test_field_values(fixtures):
    res = parse_file(fixtures / "access.nginx.log")
    ev = res.events[0]
    assert ev.ts.tzinfo is not None and ev.ts.utcoffset().total_seconds() == 0
    assert ev.method == "GET"
    assert ev.path.startswith("/")
    assert 100 <= ev.status < 600
    assert ev.bytes >= 0
    assert ev.user_agent


def test_apache_vhost_captured(fixtures):
    res = parse_file(fixtures / "access.apache.log")
    assert res.fmt == "apache"
    assert {e.host for e in res.events} == {"example-shop.test"}


def test_gzip_is_transparent(fixtures):
    plain = parse_file(fixtures / "access.nginx.log")
    gz = parse_file(fixtures / "access.nginx.log.gz")
    assert gz.fmt == "nginx"
    assert gz.parsed == plain.parsed
    assert [e.path for e in gz.events] == [e.path for e in plain.events]


def test_malformed_lines_are_skipped_not_fatal(fixtures):
    res = parse_file(fixtures / "malformed.nginx.log")
    assert res.parsed == 20
    assert res.skipped == 2


def test_format_override_beats_detection(fixtures):
    res = parse_file(fixtures / "access.nginx.log", fmt="apache")
    assert res.fmt == "apache"
    assert res.parsed == 651


def test_detect_returns_none_for_garbage():
    assert detect_format(["hello", "world", "not a log"]) is None
    assert detect_format([]) is None


def test_unknown_format_rejected(fixtures):
    with pytest.raises(ValueError):
        parse_file(fixtures / "access.nginx.log", fmt="iis")


def test_vercel_useragent_list_flattened(fixtures):
    res = parse_file(fixtures / "vercel.drain.jsonl")
    assert all(isinstance(e.user_agent, str) for e in res.events)
    assert any("GPTBot" in e.user_agent for e in res.events)


def test_cloudflare_timestamps_are_utc(fixtures):
    res = parse_file(fixtures / "cloudflare.logpush.jsonl")
    assert all(e.ts.tzinfo == timezone.utc for e in res.events)
