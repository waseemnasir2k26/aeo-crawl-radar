# aeo-crawl-radar

**See which AI crawlers actually visited your site, and which pages none of them has ever fetched.**

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) ![License MIT](https://img.shields.io/badge/license-MIT-green)

Rank trackers cannot tell you whether GPTBot or ClaudeBot came back after you rewrote a page. Your server logs can. This parses them locally.

## What it does

- Reads nginx, Apache, Cloudflare Logpush and Vercel log-drain files. Format is auto-detected and `.gz` is read in place.
- Counts hits, paths, bytes and first/last seen for 25 tracked AI crawlers (list in `src/aeo_crawl_radar/data/bots.yaml`; bring your own with `--bots`).
- Sitemap gap report: sitemap URLs that no AI crawler has ever fetched.
- Week-over-week `diff`, plus `--json` and `--csv` output.
- Optional reverse and forward DNS check (`--verify-dns`) to catch spoofed user agents.
- Stores history in a local SQLite file. No account and no data leaves the machine, apart from what you ask for (sitemap fetch, DNS lookups).

## Quickstart

```bash
git clone https://github.com/waseemnasir2k26/aeo-crawl-radar
cd aeo-crawl-radar
pip install -e .
aeo-crawl-radar scan /var/log/nginx/access.log
aeo-crawl-radar scan /var/log/nginx/access.log.*.gz     # backfill history
aeo-crawl-radar diff --weeks 2
aeo-crawl-radar gaps --sitemap https://yoursite.com/sitemap.xml
```

Needs Python 3.11+. To try it first, point `scan` at the synthetic logs in `tests/fixtures/`; the sample dashboard people see in screenshots comes from those fixtures, not from a live site.

## For you if

You do AEO/GEO work, you have raw access logs, and you want evidence that answer engines fetched the pages you fixed.

## Limits

- Logs only. Requests served from a CDN cache, blocked at a WAF, or hosted without log access never show up.
- A fetch is not a citation, and a crawl is not referral traffic.
- User agents can be faked. Without `--verify-dns` every count is an upper bound. Some vendors (Bytespider, CCBot, Meta) publish no resolvable hostname, so those rows stay "unverified".
- Vendors rename and retire crawlers; the bot list is a snapshot.
- Not published to PyPI, so install from the clone as shown.
- Last reviewed October 2026.

## Built by SkynetLabs

Built by [SkynetLabs](https://skynetjoe.com). Questions: info@skynetjoe.com

Need this wired into your business? SkynetLabs builds voice agents, n8n back offices and sites that convert → https://skynetjoe.com
