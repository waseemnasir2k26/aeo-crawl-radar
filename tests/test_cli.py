import json

import pytest

from aeo_crawl_radar.cli import main
from aeo_crawl_radar.dnsverify import FAILED, UNSUPPORTED, VERIFIED, DNSVerifier


def run(args, capsys):
    code = main(args)
    out, err = capsys.readouterr()
    return code, out, err


def test_scan_prints_dashboard(db_path, fixtures, capsys):
    code, out, err = run(
        ["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path)], capsys
    )
    assert code == 0
    assert "AI CRAWL RADAR" in out
    assert "GPTBot" in out and "ClaudeBot" in out
    assert "TOP PATHS" in out and "STATUS CODES" in out
    assert "REFERENCE (NON-AI) CRAWLERS" in out and "Googlebot" in out
    assert "651" in err and "491" in err


def test_scan_gz(db_path, fixtures, capsys):
    code, out, _ = run(
        ["scan", str(fixtures / "access.nginx.log.gz"), "--db", str(db_path)], capsys
    )
    assert code == 0 and "GPTBot" in out


def test_scan_missing_file_exits_2(db_path, tmp_path, capsys):
    code, _, err = run(["scan", str(tmp_path / "nope.log"), "--db", str(db_path)], capsys)
    assert code == 2 and "no such log file" in err


def test_scan_json_export(db_path, fixtures, capsys):
    code, out, _ = run(
        ["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path), "--json"],
        capsys,
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["summary"]["ai_hits"] == 388
    assert payload["summary"]["reference_hits"] == 103
    assert any(b["bot"] == "PerplexityBot" for b in payload["summary"]["bots"])


def test_scan_csv_export_to_file(db_path, fixtures, tmp_path, capsys):
    out_csv = tmp_path / "hits.csv"
    code, _, _ = run(
        [
            "scan", str(fixtures / "access.nginx.log"),
            "--db", str(db_path), "--csv", str(out_csv),
        ],
        capsys,
    )
    assert code == 0
    lines = out_csv.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("ts,ip,host,method,path,status,bytes,ua,bot")
    assert len(lines) == 389          # header + 388 AI hits


def test_report_then_diff_then_gaps(db_path, fixtures, capsys):
    assert main(["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path)]) == 0
    capsys.readouterr()

    code, out, _ = run(["report", "--db", str(db_path)], capsys)
    assert code == 0 and "AI CRAWL RADAR" in out

    code, out, _ = run(["diff", "--weeks", "2", "--db", str(db_path)], capsys)
    assert code == 0 and "CRAWL DIFF" in out and "CCBot" in out

    code, out, _ = run(
        ["gaps", "--sitemap", str(fixtures / "sitemap.xml"), "--db", str(db_path),
         "--top", "50"],
        capsys,
    )
    assert code == 0
    assert "SITEMAP GAP REPORT" in out
    assert "NEVER FETCHED BY ANY AI CRAWLER" in out
    assert "/services/aeo-retainer" in out
    assert "/blog/what-is-aeo" not in out.split("NEVER FETCHED")[1]


def test_gaps_json(db_path, fixtures, capsys):
    main(["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path)])
    capsys.readouterr()
    code, out, _ = run(
        ["gaps", "--sitemap", str(fixtures / "sitemap.xml"), "--db", str(db_path),
         "--json"],
        capsys,
    )
    payload = json.loads(out)
    assert code == 0
    assert payload["total_urls"] == 22
    assert len(payload["never_crawled"]) == 10
    assert payload["coverage_pct"] == 54.5


def test_report_on_empty_db_is_a_clear_error(db_path, capsys):
    code, _, err = run(["report", "--db", str(db_path)], capsys)
    assert code == 1 and "no hits yet" in err


def test_since_filter_narrows_the_dashboard(db_path, fixtures, capsys):
    main(["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path)])
    capsys.readouterr()
    code, out, _ = run(
        ["report", "--db", str(db_path), "--since", "2026-08-24", "--json"], capsys
    )
    assert code == 0
    assert json.loads(out)["summary"]["ai_hits"] < 388


def test_bots_command_lists_taxonomy(capsys):
    code, out, _ = run(["bots"], capsys)
    assert code == 0
    assert "GPTBot" in out and "OpenAI" in out
    assert "reference" in out and "Googlebot" in out
    assert out.count("\n") > 25


def test_custom_bots_file_used_by_scan(db_path, fixtures, tmp_path, capsys):
    custom = tmp_path / "bots.yaml"
    custom.write_text(
        "bots:\n"
        "  - name: OnlyClaude\n"
        "    vendor: Anthropic\n"
        "    ua_regex: 'ClaudeBot'\n"
        "    purpose: training\n"
        "    docs: https://example.test\n",
        encoding="utf-8",
    )
    code, out, _ = run(
        ["scan", str(fixtures / "access.nginx.log"), "--db", str(db_path),
         "--bots", str(custom), "--json"],
        capsys,
    )
    payload = json.loads(out)
    assert code == 0
    assert [b["bot"] for b in payload["summary"]["bots"]] == ["OnlyClaude"]
    assert payload["summary"]["ai_hits"] == 61


def test_bad_time_value_is_rejected(db_path, capsys):
    code, _, err = run(["report", "--db", str(db_path), "--since", "last tuesday"], capsys)
    assert code == 2
    assert "cannot parse time" in err


# --- DNS verification ------------------------------------------------------
class _FakeVerifier(DNSVerifier):
    """No network in tests: a stub resolver with one honest and one spoofed IP."""

    RDNS = {"203.0.113.11": "crawl-203-0-113-11.gptbot.openai.com"}
    FWD = {"crawl-203-0-113-11.gptbot.openai.com": {"203.0.113.11"}}

    def _reverse(self, ip):
        return self.RDNS.get(ip)

    def _forward(self, host):
        return self.FWD.get(host, set())


def test_dns_verifier_states():
    v = _FakeVerifier()
    assert v.verify("203.0.113.11", [".openai.com"]) == VERIFIED
    assert v.verify("203.0.113.99", [".openai.com"]) == FAILED   # spoofed UA
    assert v.verify("192.0.2.111", []) == UNSUPPORTED            # no published suffix
    assert v.verify("", [".openai.com"]) == FAILED


def test_dns_verifier_caches_per_ip():
    v = _FakeVerifier()
    v.verify("203.0.113.11", [".openai.com"])
    v.verify("203.0.113.11", [".openai.com"])
    assert v.lookups == 1


def test_verified_and_failed_land_in_the_dashboard(db_path, fixtures, taxonomy, capsys):
    from aeo_crawl_radar.cli import ingest
    from aeo_crawl_radar.store import Store

    store = Store(db_path)
    ingest([fixtures / "access.nginx.log"], store, taxonomy, verifier=_FakeVerifier())
    rows = {r["bot"]: r for r in store.bot_summary()}
    assert rows["GPTBot"]["verified_hits"] > 0
    assert rows["GPTBot"]["failed_hits"] > 0        # the other two GPTBot IPs
    assert rows["CCBot"]["verified_hits"] == 0      # no published DNS suffix
    text = __import__("aeo_crawl_radar.report", fromlist=["report"]).render_dashboard(
        __import__("aeo_crawl_radar.report", fromlist=["report"]).build_summary(store)
    )
    assert "ok /" in text and "unverified" in text
    store.close()
