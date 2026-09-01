"""aeo-crawl-radar command line interface."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__, report
from .bots import BotTaxonomy
from .dnsverify import UNCHECKED, DNSVerifier
from .parsers import FORMATS, parse_file
from .sitemap import gap_report, load_sitemap
from .store import DEFAULT_DB, IngestStats, Store, fingerprint

_REL = re.compile(r"^(\d+)\s*([hdwm])$", re.IGNORECASE)
_UNITS = {"h": "hours", "d": "days", "w": "weeks"}


def parse_when(value: str | None) -> datetime | None:
    """Accept ISO dates/datetimes or relative offsets like 7d, 12h, 2w, 3m."""
    if not value:
        return None
    v = value.strip()
    m = _REL.match(v)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta = timedelta(days=n * 30) if unit == "m" else timedelta(**{_UNITS[unit]: n})
        return datetime.now(timezone.utc) - delta
    iso = v.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"cannot parse time {value!r}; use ISO (2026-08-01) or relative (7d, 12h, 2w)"
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _emit(text: str, target: str | None) -> None:
    if target in (None, "", "-"):
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    else:
        Path(target).write_text(text, encoding="utf-8")
        sys.stderr.write(f"wrote {target}\n")


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------
def ingest(paths, store: Store, taxonomy: BotTaxonomy, fmt=None, verifier=None,
           since=None, until=None) -> tuple[IngestStats, list[str]]:
    stats = IngestStats()
    formats: list[str] = []
    rows = []
    for path in paths:
        result = parse_file(path, fmt)
        formats.append(result.fmt)
        stats.parsed += result.parsed
        stats.skipped += result.skipped
        for ev in result.events:
            if since and ev.ts < since:
                continue
            if until and ev.ts > until:
                continue
            bot = taxonomy.match(ev.user_agent)
            if bot is None:
                continue
            stats.bot_hits += 1
            verified = UNCHECKED
            if verifier is not None:
                verified = verifier.verify(ev.ip, bot.verify_dns)
            rows.append(
                {
                    "fp": fingerprint(ev, bot.name),
                    "ts": ev.ts.astimezone(timezone.utc).isoformat(),
                    "ts_epoch": int(ev.ts.timestamp()),
                    "ip": ev.ip,
                    "host": ev.host,
                    "method": ev.method,
                    "path": ev.path,
                    "status": ev.status,
                    "bytes": ev.bytes,
                    "ua": ev.user_agent,
                    "bot": bot.name,
                    "vendor": bot.vendor,
                    "purpose": bot.purpose,
                    "is_ai": bot.ai,
                    "verified": verified,
                    "source": ev.source,
                }
            )
    inserted, dupes = store.add_hits(rows)
    stats.inserted, stats.duplicates = inserted, dupes
    store.record_run([str(p) for p in paths], formats, stats)
    return stats, formats


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def _outputs(args, store, since, until, gap=None) -> None:
    summary = report.build_summary(store, since, until, top=args.top)
    if args.json is not None:
        payload = {"summary": summary}
        if gap is not None:
            payload["sitemap_gap"] = {
                "total_urls": gap.total_urls,
                "coverage_pct": round(gap.coverage, 1),
                "never_crawled": gap.never_crawled,
                "crawled": [{"url": u, "bots": b} for u, b in gap.crawled],
            }
        _emit(report.to_json(payload), args.json)
    if args.csv is not None:
        _emit(report.to_csv(store.rows(since, until)), args.csv)
    if args.json is None and args.csv is None:
        sys.stdout.write(report.render_dashboard(summary))
        if gap is not None:
            sys.stdout.write(report.render_gap(gap))


def cmd_scan(args) -> int:
    taxonomy = BotTaxonomy.from_file(args.bots)
    since, until = parse_when(args.since), parse_when(args.until)
    verifier = DNSVerifier() if args.verify_dns else None
    missing = [p for p in args.logfile if not Path(p).exists()]
    if missing:
        sys.stderr.write("no such log file: " + ", ".join(missing) + "\n")
        return 2
    with Store(args.db) as store:
        stats, formats = ingest(
            args.logfile, store, taxonomy, args.format, verifier, since, until
        )
        sys.stderr.write(
            f"parsed {stats.parsed:,} lines ({stats.skipped:,} unparseable) "
            f"as {'/'.join(sorted(set(formats)))}; {stats.bot_hits:,} crawler hits; "
            f"{stats.inserted:,} new rows, {stats.duplicates:,} already stored"
            + (f"; {verifier.lookups} DNS lookups" if verifier else "")
            + "\n"
        )
        gap = None
        if args.sitemap:
            gap = gap_report(load_sitemap(args.sitemap), store.path_bot_map(since, until))
        _outputs(args, store, since, until, gap)
    return 0


def cmd_report(args) -> int:
    since, until = parse_when(args.since), parse_when(args.until)
    with Store(args.db) as store:
        if store.count() == 0:
            sys.stderr.write(f"{args.db} has no hits yet; run `aeo-crawl-radar scan` first\n")
            return 1
        gap = None
        if args.sitemap:
            gap = gap_report(load_sitemap(args.sitemap), store.path_bot_map(since, until))
        _outputs(args, store, since, until, gap)
    return 0


def cmd_diff(args) -> int:
    with Store(args.db) as store:
        if store.count() == 0:
            sys.stderr.write(f"{args.db} has no hits yet; run `aeo-crawl-radar scan` first\n")
            return 1
        d = report.build_diff(store, weeks=args.weeks, until=parse_when(args.until))
        if args.json is not None:
            _emit(report.to_json(d), args.json)
        else:
            sys.stdout.write(report.render_diff(d))
    return 0


def cmd_gaps(args) -> int:
    since, until = parse_when(args.since), parse_when(args.until)
    with Store(args.db) as store:
        gap = gap_report(load_sitemap(args.sitemap), store.path_bot_map(since, until))
        if args.json is not None:
            _emit(
                report.to_json(
                    {
                        "total_urls": gap.total_urls,
                        "coverage_pct": round(gap.coverage, 1),
                        "never_crawled": gap.never_crawled,
                        "crawled": [{"url": u, "bots": b} for u, b in gap.crawled],
                    }
                ),
                args.json,
            )
        elif args.csv is not None:
            _emit(
                report.to_csv(
                    [{"url": u, "crawled": "no", "bots": ""} for u in gap.never_crawled]
                    + [{"url": u, "crawled": "yes", "bots": " ".join(b)}
                       for u, b in gap.crawled],
                    headers=["url", "crawled", "bots"],
                ),
                args.csv,
            )
        else:
            sys.stdout.write(report.render_gap(gap, limit=args.top))
    return 0


def cmd_bots(args) -> int:
    taxonomy = BotTaxonomy.from_file(args.bots)
    rows = [
        [b.name, b.vendor, b.purpose, "ai" if b.ai else "reference",
         "yes" if b.verify_dns else "no", b.docs]
        for b in taxonomy.bots
    ]
    sys.stdout.write(
        report.render_table(
            ["BOT", "VENDOR", "PURPOSE", "CLASS", "DNS-VERIFIABLE", "DOCS"], rows
        )
        + "\n"
    )
    return 0


# --------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="aeo-crawl-radar",
        description="Which AI crawlers actually visited your site, from your own logs.",
    )
    p.add_argument("--version", action="version", version=f"aeo-crawl-radar {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp, window=True, exports=True):
        sp.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default {DEFAULT_DB})")
        if window:
            sp.add_argument("--since", help="ISO date or relative offset (7d, 12h, 2w)")
            sp.add_argument("--until", help="ISO date or relative offset")
        if exports:
            sp.add_argument("--json", nargs="?", const="-", help="emit JSON (optional path)")
            sp.add_argument("--csv", nargs="?", const="-", help="emit CSV (optional path)")
        sp.add_argument("--top", type=int, default=10, help="rows in top-N lists")

    s = sub.add_parser("scan", help="parse log files into the store and print the dashboard")
    s.add_argument("logfile", nargs="+", help="access log(s); .gz is read transparently")
    s.add_argument("--format", choices=FORMATS, help="override format auto-detection")
    s.add_argument("--bots", help="path to a custom bots.yaml")
    s.add_argument("--verify-dns", action="store_true",
                   help="reverse+forward DNS confirm crawler IPs (slow, network)")
    s.add_argument("--sitemap", help="sitemap URL or file; adds the gap report")
    common(s)
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("report", help="dashboard from what is already stored")
    r.add_argument("--sitemap", help="sitemap URL or file; adds the gap report")
    common(r)
    r.set_defaults(func=cmd_report)

    d = sub.add_parser("diff", help="compare the last N weeks against the N before")
    d.add_argument("--weeks", type=int, default=1)
    d.add_argument("--until", help="end of the current window (default: newest hit)")
    d.add_argument("--db", default=DEFAULT_DB)
    d.add_argument("--json", nargs="?", const="-")
    d.set_defaults(func=cmd_diff)

    g = sub.add_parser("gaps", help="sitemap URLs never fetched by any AI crawler")
    g.add_argument("--sitemap", required=True, help="sitemap URL or local file")
    common(g)
    g.set_defaults(func=cmd_gaps)

    b = sub.add_parser("bots", help="print the loaded bot taxonomy")
    b.add_argument("--bots", help="path to a custom bots.yaml")
    b.set_defaults(func=cmd_bots)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError, argparse.ArgumentTypeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
