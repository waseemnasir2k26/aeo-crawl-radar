# aeo-crawl-radar

Parse your own web server logs and see exactly which AI crawlers visited your site, what they fetched, and which pages they have never touched.

```
AI CRAWL RADAR
==============
window   : 2026-08-04 01:00 -> 2026-08-31 21:19
ai hits  : 388   classic search-bot hits: 103   ai share of bot traffic: 79.0%
served   : 7.0 MB to AI crawlers

AI CRAWLERS
===========
BOT                 VENDOR        PURPOSE       HITS  PATHS     BYTES  FIRST SEEN        LAST SEEN         DNS
------------------  ------------  ------------  ----  -----  --------  ----------------  ----------------  ----------
GPTBot              OpenAI        training        86     14    1.7 MB  2026-08-04 01:00  2026-08-31 04:03  unverified
ClaudeBot           Anthropic     training        61     14    1.1 MB  2026-08-04 06:30  2026-08-31 21:19  unverified
OAI-SearchBot       OpenAI        search-index    54     13  934.8 KB  2026-08-04 01:01  2026-08-30 21:19  unverified
PerplexityBot       Perplexity    search-index    44     13  840.0 KB  2026-08-04 05:37  2026-08-31 02:23  unverified
Bytespider          ByteDance     training        31     14  631.4 KB  2026-08-04 12:34  2026-08-31 11:56  unverified
ChatGPT-User        OpenAI        live-fetch      28     11  495.5 KB  2026-08-06 17:10  2026-08-30 12:46  unverified
Google-Extended     Google        training        22      9  413.4 KB  2026-08-04 16:50  2026-08-31 10:37  unverified
meta-externalagent  Meta          training        19     10  340.2 KB  2026-08-11 01:17  2026-08-31 20:39  unverified
Claude-User         Anthropic     live-fetch      17     10  268.6 KB  2026-08-05 15:37  2026-08-31 11:44  unverified
Amazonbot           Amazon        search-index    14     10  198.1 KB  2026-08-07 18:29  2026-08-30 15:05  unverified
CCBot               Common Crawl  training        12     10  183.7 KB  2026-08-18 06:09  2026-08-30 04:22  unverified

TOP PATHS (ALL AI BOTS)
=======================
PATH                       HITS  BOTS     BYTES
-------------------------  ----  ----  --------
/blog/crawl-budget-2026      38    10  602.1 KB
/services/technical-seo      36    10  723.6 KB
/blog/ai-search-checklist    34     8  663.7 KB
/faq                         32     9  570.4 KB
/llms.txt                    30    11  540.8 KB

STATUS CODES (AI BOTS)
======================
STATUS  HITS  SHARE
------  ----  -----
200      338  87.1%
304       25   6.4%
301       12   3.1%
404       11   2.8%
500        2   0.5%

SITEMAP GAP REPORT
==================
22 sitemap URLs   12 fetched by AI bots   10 NEVER fetched   coverage 54.5%

NEVER FETCHED BY ANY AI CRAWLER:
  [ ] https://example-shop.test/blog/entity-seo-primer
  [ ] https://example-shop.test/blog/measuring-ai-referrals
  [ ] https://example-shop.test/blog/schema-markup-for-answers
  [ ] https://example-shop.test/careers
  [ ] https://example-shop.test/case-studies/b2b-saas
  [ ] https://example-shop.test/case-studies/regional-retailer
  [ ] https://example-shop.test/legal/privacy
  [ ] https://example-shop.test/legal/terms
  [ ] https://example-shop.test/services/aeo-retainer
  [ ] https://example-shop.test/services/log-analysis
```

_(That is the tool's real output against the synthetic fixture logs in `tests/fixtures/`.)_

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License MIT](https://img.shields.io/badge/license-MIT-green)
![Log formats: 4](https://img.shields.io/badge/log%20formats-nginx%20%7C%20apache%20%7C%20cloudflare%20%7C%20vercel-lightgrey)
![AI crawlers: 25](https://img.shields.io/badge/AI%20crawlers%20tracked-25-orange)

## Status

Last reviewed: October 2026 · release v2026.10

## Quick start

```bash
pipx install aeo-crawl-radar          # or: pip install aeo-crawl-radar
aeo-crawl-radar scan /var/log/nginx/access.log
```

That is it. The format is sniffed, `.gz` files are read in place, hits land in `./.aeo-crawl-radar.sqlite`, and the dashboard prints.

Then, once you have more than one run stored:

```bash
aeo-crawl-radar scan /var/log/nginx/access.log.*.gz            # backfill history
aeo-crawl-radar diff --weeks 2                                 # what changed
aeo-crawl-radar gaps --sitemap https://yoursite.com/sitemap.xml
```

No config file, no account, no data leaves the machine.

## Why this matters

If you are doing AEO/GEO work — rewriting pages so answer engines can quote them — the first question anyone should ask is whether the engines came back and re-fetched the pages you fixed. Rank trackers cannot tell you that. Your access log can.

Per Similarweb's 2026 log-file analysis ([similarweb.com/blog/marketing/geo/log-file-analysis](https://www.similarweb.com/blog/marketing/geo/log-file-analysis/)):

- AI crawlers now account for roughly **40% of crawl activity** on high-traffic sites.
- AI-related crawlers made **3.6x as many requests** as traditional search crawlers.
- AI-driven traffic was **up 187% between January and December 2025**.

Commercial AEO platforms sell this readout as a monthly feature. It is a log-parsing job. This is the log parser.

## Supported log formats

| Format       | Detected by                                        | Notes                                                                                                                            |
| ------------ | -------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `nginx`      | combined layout                                    | The default `combined` LogFormat.                                                                                                |
| `apache`     | combined layout with a leading `%v:%p` vhost token | Apache's `combined` is byte-identical to nginx's; `vhost_combined` adds the host, which is captured.                             |
| `cloudflare` | JSON lines with Logpush field names                | Reads `EdgeStartTimestamp`, `ClientIP`, `ClientRequestURI`, `ClientRequestUserAgent`, `EdgeResponseStatus`, `EdgeResponseBytes`. |
| `vercel`     | JSON lines with a `proxy` object                   | Reads `timestamp` (ms) and `proxy.{clientIp,method,path,userAgent,statusCode,bytes}`.                                            |

Auto-detection sniffs the first 25 non-empty lines. Override it with `--format nginx|apache|cloudflare|vercel`. Any `.gz` file is decompressed transparently. Lines that do not parse are counted and skipped, never fatal.

### The bot list

Shipped in [`src/aeo_crawl_radar/data/bots.yaml`](src/aeo_crawl_radar/data/bots.yaml), not hardcoded. `purpose` is the vendor's stated purpose — `training` (corpus collection), `search-index` (builds an index that cites you later), `live-fetch` (fetched at runtime because a user asked something).

| Bot                  | Vendor       | Purpose      |
| -------------------- | ------------ | ------------ |
| GPTBot               | OpenAI       | training     |
| OAI-SearchBot        | OpenAI       | search-index |
| ChatGPT-User         | OpenAI       | live-fetch   |
| ClaudeBot            | Anthropic    | training     |
| Claude-SearchBot     | Anthropic    | search-index |
| Claude-User          | Anthropic    | live-fetch   |
| PerplexityBot        | Perplexity   | search-index |
| Perplexity-User      | Perplexity   | live-fetch   |
| Google-Extended      | Google       | training     |
| GoogleOther          | Google       | training     |
| Applebot-Extended    | Apple        | training     |
| Applebot             | Apple        | search-index |
| Amazonbot            | Amazon       | search-index |
| meta-externalagent   | Meta         | training     |
| meta-externalfetcher | Meta         | live-fetch   |
| Bytespider           | ByteDance    | training     |
| CCBot                | Common Crawl | training     |
| cohere-ai            | Cohere       | training     |
| Diffbot              | Diffbot      | training     |
| omgili               | Webz.io      | training     |
| Timpibot             | Timpi        | training     |
| YouBot               | You.com      | search-index |
| MistralAI-User       | Mistral AI   | live-fetch   |
| DuckAssistBot        | DuckDuckGo   | search-index |
| PetalBot             | Huawei       | search-index |

Googlebot, Bingbot, DuckDuckBot and YandexBot are also matched, as `reference_bots`, so you can compare AI crawl against classic search crawl. They are excluded from the AI totals.

**Vendors rename, split and retire crawlers regularly.** This file is a snapshot with a `docs` link per entry, not a live feed. Bring your own:

```bash
aeo-crawl-radar bots                          # print what is loaded
aeo-crawl-radar scan access.log --bots my-bots.yaml
```

## The sitemap gap report

This is the part that turns log analytics into a to-do list.

```bash
aeo-crawl-radar gaps --sitemap https://yoursite.com/sitemap.xml
```

It loads your sitemap (a `sitemapindex` is followed one level down; `.gz` sitemaps work), normalises each URL to the path form that appears in your logs, and reports **which URLs no AI crawler has ever fetched**. Trailing slashes and query strings are normalised so a `?utm_source=` hit still counts.

Every line in the "NEVER FETCHED" list is a page you are publishing that no answer engine has ever read. That is a concrete backlog: internal links to add, sitemap `lastmod` to fix, a `robots.txt` rule to loosen, or a page nobody links to.

`--since` narrows it to a window ("what has not been re-fetched since I shipped the rewrite on the 12th"), and `--json` / `--csv` give you the full list for a spreadsheet or a client report.

## Spoofing and verification

**A user-agent string is a claim, not proof.** Anyone can send `User-Agent: GPTBot` from a laptop. Scrapers do it deliberately, because sites whitelist AI crawlers. Every number in the default output is therefore "requests that _said_ they were GPTBot".

The real check is DNS, the same method Google, Bing and Apple document for their own crawlers:

```bash
aeo-crawl-radar scan access.log --verify-dns
```

For each unique client IP it does a reverse DNS lookup, requires the hostname to end with a suffix the vendor publishes (`.openai.com`, `.anthropic.com`, `.perplexity.ai`, `.googlebot.com`, `.applebot.apple.com`, ...), then forward-resolves that hostname and confirms the original IP comes back. The `DNS` column then reads `41 ok / 3 bad` per bot instead of `unverified`:

- **ok** — reverse and forward DNS both check out. Genuine.
- **bad** — the request claimed to be that crawler from an IP that does not resolve to the vendor. Treat as spoofed.
- **unverified** — that vendor publishes no resolvable crawler hostname (Bytespider, CCBot, Meta and others), so DNS cannot decide. Those rows stay claims.

Verification is off by default because it costs one DNS round trip per unique IP. Results are cached per IP within a run.

## Limitations

Be clear about what this is:

- **Logs only.** If a request never reached your origin — served from a CDN edge cache, blocked at the WAF, or handled by a static host that does not give you logs — it is not in this report. Cloudflare Logpush and the Vercel drain exist precisely for that reason.
- **No JS-rendered analytics.** Crawlers do not run your analytics tag. This tool is not a substitute for it, and your analytics is not a substitute for this.
- **It cannot see what the model did with the page.** A fetch is a fetch. Whether the content was trained on, indexed, quoted in an answer, or discarded is invisible from your side. Anyone selling you that certainty is guessing.
- **It cannot prove referral traffic.** "GPTBot fetched the page" and "someone arrived from ChatGPT" are different measurements. Correlate with referrer data yourself.
- **User-agents are spoofable** — see above. Without `--verify-dns`, every count is an upper bound.
- **The bot list ages.** New crawlers ship monthly. Check `docs` links, override with `--bots`, and send a PR.

## Contributing

Issues and PRs welcome, particularly:

- New or renamed crawlers for `data/bots.yaml` (include the vendor's docs URL — entries without a source will not be merged).
- Additional log formats (Caddy, IIS, HAProxy, Fastly, AWS ALB).
- Published DNS suffixes or IP ranges for vendors currently marked `unverified`.

```bash
git clone https://github.com/waseemnasir2k26/aeo-crawl-radar
cd aeo-crawl-radar
pip install -e ".[dev]"
python -m pytest -q
```

Fixtures are synthetic and regenerated by `python tests/fixtures/_generate.py`. Never commit a real access log — they contain visitor IPs.

---

## Work with SkynetLabs

Built by [Waseem Nasir](https://www.skynetjoe.com/?utm_source=github&utm_medium=readme&utm_campaign=aeo-crawl-radar) at SkynetLabs — n8n + AI automation for small businesses.

- Hire on Fiverr: https://www.fiverr.com/agencies/skynetjoellc
- Hire on Upwork: https://www.upwork.com/freelancers/muhammadwaseemnasir
- Book a free call: https://calendly.com/skynetlabs/schedule-a-free-consultation

## License

MIT — see [LICENSE](LICENSE).
