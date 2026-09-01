"""Terminal dashboard, weekly diff, and JSON/CSV export."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

BOX_H = "-"


def human_bytes(n) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def short_ts(value) -> str:
    if not value:
        return "-"
    return str(value)[:16].replace("T", " ")


def render_table(headers, rows, aligns=None) -> str:
    """Plain-text table. No dependencies, copy-pasteable into an email."""
    rows = [[("" if c is None else str(c)) for c in r] for r in rows]
    headers = [str(h) for h in headers]
    ncols = len(headers)
    aligns = aligns or ["l"] * ncols
    widths = [len(h) for h in headers]
    for r in rows:
        for i in range(ncols):
            widths[i] = max(widths[i], len(r[i]) if i < len(r) else 0)

    def fmt(cells):
        out = []
        for i, c in enumerate(cells):
            out.append(c.rjust(widths[i]) if aligns[i] == "r" else c.ljust(widths[i]))
        return "  ".join(out).rstrip()

    sep = "  ".join(BOX_H * w for w in widths)
    lines = [fmt(headers), sep]
    lines.extend(fmt(r) for r in rows)
    return "\n".join(lines)


def section(title: str) -> str:
    return f"\n{title}\n{'=' * len(title)}"


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------
def build_summary(store, since=None, until=None, top=10) -> dict:
    bots = store.bot_summary(since, until, ai_only=True)
    reference = [
        b for b in store.bot_summary(since, until, ai_only=False) if b["bot"] not in
        {x["bot"] for x in bots}
    ]
    ai_total = sum(b["hits"] for b in bots)
    ref_total = sum(b["hits"] for b in reference)
    lo, hi = store.time_bounds()
    return {
        "window": {
            "since": since.isoformat() if since else (lo.isoformat() if lo else None),
            "until": until.isoformat() if until else (hi.isoformat() if hi else None),
        },
        "ai_hits": ai_total,
        "reference_hits": ref_total,
        "ai_share_of_bot_traffic": round(
            ai_total / (ai_total + ref_total) * 100, 1
        ) if (ai_total + ref_total) else 0.0,
        "ai_bytes": sum(b["bytes"] or 0 for b in bots),
        "bots": bots,
        "reference_bots": reference,
        "top_paths": store.top_paths(since=since, until=until, limit=top),
        "status_breakdown": store.status_breakdown(since, until),
        "top_paths_per_bot": {
            b["bot"]: store.top_paths(bot=b["bot"], since=since, until=until, limit=5)
            for b in bots
        },
    }


def render_dashboard(summary: dict, top_per_bot: int = 3) -> str:
    out: list[str] = []
    w = summary["window"]
    out.append(section("AI CRAWL RADAR"))
    out.append(f"window   : {short_ts(w['since'])} -> {short_ts(w['until'])}")
    out.append(
        f"ai hits  : {summary['ai_hits']:,}   "
        f"classic search-bot hits: {summary['reference_hits']:,}   "
        f"ai share of bot traffic: {summary['ai_share_of_bot_traffic']}%"
    )
    out.append(f"served   : {human_bytes(summary['ai_bytes'])} to AI crawlers")

    out.append(section("AI CRAWLERS"))
    rows = []
    for b in summary["bots"]:
        verified = b.get("verified_hits") or 0
        failed = b.get("failed_hits") or 0
        if verified or failed:
            vtag = f"{verified} ok / {failed} bad"
        else:
            vtag = "unverified"
        rows.append(
            [
                b["bot"],
                b["vendor"],
                b["purpose"],
                f"{b['hits']:,}",
                b["paths"],
                human_bytes(b["bytes"]),
                short_ts(b["first_seen"]),
                short_ts(b["last_seen"]),
                vtag,
            ]
        )
    if rows:
        out.append(
            render_table(
                ["BOT", "VENDOR", "PURPOSE", "HITS", "PATHS", "BYTES",
                 "FIRST SEEN", "LAST SEEN", "DNS"],
                rows,
                ["l", "l", "l", "r", "r", "r", "l", "l", "l"],
            )
        )
    else:
        out.append("no AI crawler hits in this window")

    if summary["reference_bots"]:
        out.append(section("REFERENCE (NON-AI) CRAWLERS"))
        out.append(
            render_table(
                ["BOT", "VENDOR", "HITS", "PATHS", "BYTES"],
                [
                    [b["bot"], b["vendor"], f"{b['hits']:,}", b["paths"],
                     human_bytes(b["bytes"])]
                    for b in summary["reference_bots"]
                ],
                ["l", "l", "r", "r", "r"],
            )
        )

    out.append(section("TOP PATHS (ALL AI BOTS)"))
    if summary["top_paths"]:
        out.append(
            render_table(
                ["PATH", "HITS", "BOTS", "BYTES"],
                [
                    [p["path"], f"{p['hits']:,}", p["bots"], human_bytes(p["bytes"])]
                    for p in summary["top_paths"]
                ],
                ["l", "r", "r", "r"],
            )
        )
    else:
        out.append("nothing fetched")

    if summary["top_paths_per_bot"]:
        out.append(section("TOP PATHS PER BOT"))
        for bot, paths in summary["top_paths_per_bot"].items():
            head = ", ".join(
                f"{p['path']} ({p['hits']})" for p in paths[:top_per_bot]
            )
            out.append(f"{bot:<22} {head or '-'}")

    out.append(section("STATUS CODES (AI BOTS)"))
    total = sum(s["hits"] for s in summary["status_breakdown"]) or 1
    out.append(
        render_table(
            ["STATUS", "HITS", "SHARE"],
            [
                [s["status"], f"{s['hits']:,}", f"{s['hits'] / total * 100:.1f}%"]
                for s in summary["status_breakdown"]
            ],
            ["l", "r", "r"],
        )
    )
    return "\n".join(out) + "\n"


def render_gap(rep, limit: int = 40) -> str:
    out = [section("SITEMAP GAP REPORT")]
    out.append(
        f"{rep.total_urls} sitemap URLs   "
        f"{len(rep.crawled)} fetched by AI bots   "
        f"{len(rep.never_crawled)} NEVER fetched   "
        f"coverage {rep.coverage:.1f}%"
    )
    if rep.never_crawled:
        out.append("")
        out.append("NEVER FETCHED BY ANY AI CRAWLER:")
        for u in rep.never_crawled[:limit]:
            out.append(f"  [ ] {u}")
        if len(rep.never_crawled) > limit:
            out.append(f"  ... and {len(rep.never_crawled) - limit} more (use --json)")
    else:
        out.append("every sitemap URL has been fetched by at least one AI crawler")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# weekly diff
# --------------------------------------------------------------------------
def build_diff(store, weeks: int = 1, until: datetime | None = None) -> dict:
    """Compare the last `weeks` weeks against the `weeks` weeks before that."""
    lo, hi = store.time_bounds()
    end = until or hi or datetime.now(timezone.utc)
    span = timedelta(weeks=weeks)
    cur_start, prev_start = end - span, end - (span * 2)

    cur = {b["bot"]: b for b in store.bot_summary(cur_start, end)}
    prev = {b["bot"]: b for b in store.bot_summary(prev_start, cur_start)}

    rows = []
    for bot in sorted(set(cur) | set(prev)):
        c = cur.get(bot, {}).get("hits", 0)
        p = prev.get(bot, {}).get("hits", 0)
        rows.append(
            {
                "bot": bot,
                "vendor": (cur.get(bot) or prev.get(bot))["vendor"],
                "current": c,
                "previous": p,
                "delta": c - p,
                "pct": (None if p == 0 else round((c - p) / p * 100, 1)),
                "state": "new" if p == 0 and c else ("gone" if c == 0 else "changed"),
            }
        )

    cur_paths = store.crawled_paths(cur_start, end)
    prev_paths = store.crawled_paths(prev_start, cur_start)
    return {
        "weeks": weeks,
        "current_window": [cur_start.isoformat(), end.isoformat()],
        "previous_window": [prev_start.isoformat(), cur_start.isoformat()],
        "current_hits": sum(r["current"] for r in rows),
        "previous_hits": sum(r["previous"] for r in rows),
        "bots": rows,
        "new_paths": sorted(cur_paths - prev_paths),
        "dropped_paths": sorted(prev_paths - cur_paths),
    }


def render_diff(d: dict, limit: int = 20) -> str:
    out = [section(f"CRAWL DIFF - LAST {d['weeks']}w VS PRIOR {d['weeks']}w")]
    out.append(
        f"current : {short_ts(d['current_window'][0])} -> {short_ts(d['current_window'][1])}"
        f"   {d['current_hits']:,} hits"
    )
    out.append(
        f"previous: {short_ts(d['previous_window'][0])} -> {short_ts(d['previous_window'][1])}"
        f"   {d['previous_hits']:,} hits"
    )
    rows = []
    for r in d["bots"]:
        pct = "new" if r["pct"] is None and r["current"] else (
            "-" if r["pct"] is None else f"{r['pct']:+.1f}%"
        )
        rows.append(
            [r["bot"], r["vendor"], r["previous"], r["current"],
             f"{r['delta']:+d}", pct, r["state"]]
        )
    out.append("")
    out.append(
        render_table(
            ["BOT", "VENDOR", "PREV", "NOW", "DELTA", "CHANGE", "STATE"],
            rows,
            ["l", "l", "r", "r", "r", "r", "l"],
        )
        if rows
        else "no crawler activity in either window"
    )
    if d["new_paths"]:
        out.append(f"\nNEWLY CRAWLED PATHS ({len(d['new_paths'])}):")
        out.extend(f"  + {p}" for p in d["new_paths"][:limit])
    if d["dropped_paths"]:
        out.append(f"\nNO LONGER CRAWLED ({len(d['dropped_paths'])}):")
        out.extend(f"  - {p}" for p in d["dropped_paths"][:limit])
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
def to_json(payload) -> str:
    return json.dumps(payload, indent=2, default=str)


def to_csv(rows, headers=None) -> str:
    rows = list(rows)
    if not rows:
        return ""
    headers = headers or list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()
