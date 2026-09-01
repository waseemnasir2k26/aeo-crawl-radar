"""Regenerate the synthetic fixture logs.

Run:  python tests/fixtures/_generate.py

Everything here is invented: the domain, the IPs (documentation ranges),
the paths and the traffic mix. No real customer log ever enters this repo.
Output is deterministic (fixed seed) so fixtures only change when this
script changes.
"""

from __future__ import annotations

import gzip
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
SEED = 20260901
HOST = "example-shop.test"

# Fixed 4-week span so `diff --weeks 2` has a populated current and previous
# window without depending on the wall clock.
END = datetime(2026, 8, 31, 23, 0, tzinfo=timezone.utc)
START = END - timedelta(weeks=4)
MID = END - timedelta(weeks=2)

AI_UAS = {
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot",
    "OAI-SearchBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "ChatGPT-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ChatGPT-User/1.0; +https://openai.com/bot",
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; ClaudeBot/1.0; +claudebot@anthropic.com",
    "Claude-User": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; Claude-User/1.0; +Claude-User@anthropic.com",
    "PerplexityBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot",
    "Google-Extended": "Mozilla/5.0 (compatible; Google-Extended/1.0; +http://www.google.com/bot.html)",
    "Bytespider": "Mozilla/5.0 (Linux; Android 5.0) AppleWebKit/537.36 (KHTML, like Gecko) Mobile Safari/537.36 (compatible; Bytespider; spider-feedback@bytedance.com)",
    "Amazonbot": "Mozilla/5.0 (Linux; like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 (compatible; Amazonbot/0.1; +https://developer.amazon.com/support/amazonbot)",
    "meta-externalagent": "meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)",
    "CCBot": "CCBot/2.0 (https://commoncrawl.org/faq/)",
}

REF_UAS = {
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
}

HUMAN_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
]

# Paths the bots actually fetch. A deliberate subset of the sitemap, so the
# gap report has something real to report.
CRAWLED_PATHS = [
    "/",
    "/pricing",
    "/about",
    "/contact",
    "/blog/ai-search-checklist",
    "/blog/what-is-aeo",
    "/blog/llms-txt-explained",
    "/blog/crawl-budget-2026",
    "/services/technical-seo",
    "/services/content-audit",
    "/llms.txt",
    "/robots.txt",
    "/sitemap.xml",
    "/faq",
]

# In the sitemap but never fetched by an AI bot -> the gap report's payload.
UNCRAWLED_PATHS = [
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
]

# Documentation / example IP ranges only (RFC 5737, RFC 3849).
BOT_IPS = {
    "GPTBot": ["203.0.113.11", "203.0.113.12", "203.0.113.13"],
    "OAI-SearchBot": ["203.0.113.21", "203.0.113.22"],
    "ChatGPT-User": ["203.0.113.31"],
    "ClaudeBot": ["198.51.100.41", "198.51.100.42"],
    "Claude-User": ["198.51.100.51"],
    "PerplexityBot": ["198.51.100.61", "198.51.100.62"],
    "Google-Extended": ["192.0.2.71"],
    "Bytespider": ["192.0.2.81", "192.0.2.82"],
    "Amazonbot": ["192.0.2.91"],
    "meta-externalagent": ["192.0.2.101"],
    "CCBot": ["192.0.2.111"],
    "Googlebot": ["192.0.2.121", "192.0.2.122"],
    "Bingbot": ["192.0.2.131"],
}

# hits over the whole 4 weeks; second value = share landing in the recent 2 weeks
VOLUME = {
    "GPTBot": (86, 0.62),
    "OAI-SearchBot": (54, 0.70),
    "ChatGPT-User": (28, 0.79),
    "ClaudeBot": (61, 0.57),
    "Claude-User": (17, 0.82),
    "PerplexityBot": (44, 0.61),
    "Google-Extended": (22, 0.45),
    "Bytespider": (31, 0.19),   # tails off in the recent window
    "Amazonbot": (14, 0.50),
    "meta-externalagent": (19, 0.68),
    "CCBot": (12, 1.00),        # only appears in the recent window -> "new"
    "Googlebot": (70, 0.50),
    "Bingbot": (33, 0.48),
}


def _ts(rng, recent):
    lo, hi = (MID, END) if recent else (START, MID)
    span = int((hi - lo).total_seconds())
    return lo + timedelta(seconds=rng.randrange(span))


def _status(rng, path):
    if path == "/blog/crawl-budget-2026" and rng.random() < 0.25:
        return 404
    r = rng.random()
    if r < 0.90:
        return 200
    if r < 0.96:
        return 304
    return 500 if r > 0.985 else 301


def _bytes(rng, status):
    if status in (301, 304):
        return 0
    if status == 404:
        return rng.randrange(400, 900)
    return rng.randrange(1800, 42000)


def build_events():
    rng = random.Random(SEED)
    events = []
    for bot, (total, recent_share) in VOLUME.items():
        ua = AI_UAS.get(bot) or REF_UAS[bot]
        ips = BOT_IPS[bot]
        n_recent = round(total * recent_share)
        for i in range(total):
            recent = i < n_recent
            path = rng.choice(CRAWLED_PATHS)
            status = _status(rng, path)
            events.append(
                {
                    "ts": _ts(rng, recent),
                    "ip": rng.choice(ips),
                    "method": "GET",
                    "path": path,
                    "status": status,
                    "bytes": _bytes(rng, status),
                    "ua": ua,
                }
            )
    # Human traffic: the noise the parser has to walk past.
    all_paths = CRAWLED_PATHS + UNCRAWLED_PATHS
    for i in range(160):
        path = rng.choice(all_paths)
        status = _status(rng, path)
        events.append(
            {
                "ts": _ts(rng, i % 2 == 0),
                "ip": f"198.51.100.{rng.randrange(150, 250)}",
                "method": rng.choice(["GET"] * 9 + ["POST"]),
                "path": path,
                "status": status,
                "bytes": _bytes(rng, status),
                "ua": rng.choice(HUMAN_UAS),
            }
        )
    events.sort(key=lambda e: e["ts"])
    return events


def nginx_line(e):
    ts = e["ts"].strftime("%d/%b/%Y:%H:%M:%S +0000")
    return (
        f'{e["ip"]} - - [{ts}] "{e["method"]} {e["path"]} HTTP/1.1" '
        f'{e["status"]} {e["bytes"]} "-" "{e["ua"]}"'
    )


def apache_line(e):
    return f"{HOST}:443 " + nginx_line(e)


def cloudflare_line(e):
    return json.dumps(
        {
            "ClientIP": e["ip"],
            "ClientRequestHost": HOST,
            "ClientRequestMethod": e["method"],
            "ClientRequestURI": e["path"],
            "ClientRequestUserAgent": e["ua"],
            "EdgeResponseBytes": e["bytes"],
            "EdgeResponseStatus": e["status"],
            "EdgeStartTimestamp": e["ts"].strftime("%Y-%m-%dT%H:%M:%SZ"),
            "RayID": f"{abs(hash((e['ip'], e['ts'].isoformat()))) % (16**16):016x}",
        },
        sort_keys=True,
    )


def vercel_line(e):
    return json.dumps(
        {
            "deploymentId": "dpl_5xKq2AeoRadarFixture",
            "id": f"{abs(hash((e['path'], e['ts'].isoformat()))) % (10**18):018d}",
            "projectId": "prj_aeoCrawlRadarFixture",
            "proxy": {
                "clientIp": e["ip"],
                "host": HOST,
                "method": e["method"],
                "path": e["path"],
                "scheme": "https",
                "statusCode": e["status"],
                "userAgent": [e["ua"]],
                "bytes": e["bytes"],
            },
            "requestId": f"req_{abs(hash(e['ua'])) % (16**12):012x}",
            "source": "lambda",
            "timestamp": int(e["ts"].timestamp() * 1000),
        },
        sort_keys=True,
    )


def sitemap_xml():
    urls = sorted(set(CRAWLED_PATHS + UNCRAWLED_PATHS))
    # /robots.txt and /sitemap.xml are fetched but never listed in a sitemap.
    urls = [u for u in urls if u not in ("/robots.txt", "/sitemap.xml")]
    body = "\n".join(
        f"  <url>\n    <loc>https://{HOST}{u}</loc>\n"
        f"    <lastmod>2026-08-20</lastmod>\n  </url>"
        for u in urls
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n</urlset>\n"
    )


def main():
    events = build_events()
    (HERE / "access.nginx.log").write_text(
        "\n".join(nginx_line(e) for e in events) + "\n", encoding="utf-8", newline="\n"
    )
    (HERE / "access.apache.log").write_text(
        "\n".join(apache_line(e) for e in events) + "\n", encoding="utf-8", newline="\n"
    )
    (HERE / "cloudflare.logpush.jsonl").write_text(
        "\n".join(cloudflare_line(e) for e in events) + "\n", encoding="utf-8", newline="\n"
    )
    (HERE / "vercel.drain.jsonl").write_text(
        "\n".join(vercel_line(e) for e in events) + "\n", encoding="utf-8", newline="\n"
    )
    with gzip.open(HERE / "access.nginx.log.gz", "wt", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(nginx_line(e) for e in events) + "\n")
    (HERE / "sitemap.xml").write_text(sitemap_xml(), encoding="utf-8", newline="\n")
    # A file with a couple of deliberately broken lines for the skip counter.
    good = [nginx_line(e) for e in events[:20]]
    good.insert(5, "this is not a log line at all")
    good.insert(11, '203.0.113.99 - - [not-a-date] "GET / HTTP/1.1" 200 12 "-" "GPTBot"')
    (HERE / "malformed.nginx.log").write_text(
        "\n".join(good) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(events)} events written to {HERE}")


if __name__ == "__main__":
    main()
