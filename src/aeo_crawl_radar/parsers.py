"""Log parsers: nginx combined, Apache combined/vhost, Cloudflare Logpush, Vercel drain.

Every parser yields LogEvent objects and never raises on a malformed line - bad
lines are counted so the CLI can report a parse ratio instead of dying on line 3
of a 4 GB file.
"""

from __future__ import annotations

import gzip
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

FORMATS = ("nginx", "apache", "cloudflare", "vercel")


@dataclass
class LogEvent:
    ts: datetime
    ip: str
    method: str
    path: str
    status: int
    bytes: int
    user_agent: str
    host: str = ""
    source: str = ""


@dataclass
class ParseResult:
    events: list[LogEvent]
    parsed: int = 0
    skipped: int = 0
    fmt: str = ""


# --------------------------------------------------------------------------
# common / combined log format
# --------------------------------------------------------------------------
_COMBINED = re.compile(
    r"""^
    (?:(?P<vhost>[A-Za-z0-9._-]+(?::\d+)?)\s+)?   # optional apache %v:%p prefix
    (?P<ip>\S+)\s+\S+\s+(?P<user>\S+)\s+
    \[(?P<ts>[^\]]+)\]\s+
    "(?P<method>[A-Z_]+)\s+(?P<path>[^"\s]*)(?:\s+(?P<proto>HTTP/[0-9.]+))?"\s+
    (?P<status>\d{3})\s+(?P<bytes>\d+|-)
    (?:\s+"(?P<referer>[^"]*)"\s+"(?P<ua>[^"]*)")?
    """,
    re.VERBOSE,
)

_TS_FMT = "%d/%b/%Y:%H:%M:%S %z"


def _parse_clf_ts(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, _TS_FMT).astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_combined_line(line: str, source: str) -> LogEvent | None:
    m = _COMBINED.match(line.strip())
    if not m:
        return None
    ts = _parse_clf_ts(m.group("ts"))
    if ts is None:
        return None
    nbytes = m.group("bytes")
    vhost = m.group("vhost") or ""
    return LogEvent(
        ts=ts,
        ip=m.group("ip"),
        method=m.group("method"),
        path=m.group("path") or "/",
        status=int(m.group("status")),
        bytes=0 if nbytes in (None, "-") else int(nbytes),
        user_agent=m.group("ua") or "",
        host=vhost.split(":")[0],
        source=source,
    )


def parse_nginx(lines: Iterable[str], source: str = "") -> Iterator["LogEvent | None"]:
    for line in lines:
        if not line.strip():
            continue
        yield _parse_combined_line(line, source)


# Apache's "combined" layout is byte-identical to nginx's; the only practical
# difference in the wild is the optional leading vhost token produced by
# LogFormat vhost_combined. Same regex, separate name so --format apache
# means something to the user.
parse_apache = parse_nginx


# --------------------------------------------------------------------------
# JSON-lines: Cloudflare Logpush and Vercel log drain
# --------------------------------------------------------------------------
def _iso_or_epoch(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        # Cloudflare can emit unix nanoseconds; Vercel emits milliseconds.
        if v > 1e17:
            v /= 1e9
        elif v > 1e14:
            v /= 1e6
        elif v > 1e11:
            v /= 1e3
        try:
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit():
            return _iso_or_epoch(int(s))
        s = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _first_str(value) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return "" if value is None else str(value)


def _cloudflare_event(rec: dict, source: str) -> LogEvent | None:
    ts = _iso_or_epoch(rec.get("EdgeStartTimestamp") or rec.get("Datetime"))
    if ts is None:
        return None
    path = rec.get("ClientRequestURI") or rec.get("ClientRequestPath") or "/"
    return LogEvent(
        ts=ts,
        ip=rec.get("ClientIP", "") or "",
        method=rec.get("ClientRequestMethod", "GET") or "GET",
        path=path,
        status=int(rec.get("EdgeResponseStatus") or 0),
        bytes=int(rec.get("EdgeResponseBytes") or 0),
        user_agent=rec.get("ClientRequestUserAgent", "") or "",
        host=rec.get("ClientRequestHost", "") or "",
        source=source,
    )


def _vercel_event(rec: dict, source: str) -> LogEvent | None:
    proxy = rec.get("proxy") or {}
    ts = _iso_or_epoch(rec.get("timestamp") or proxy.get("timestamp"))
    if ts is None:
        return None
    status = proxy.get("statusCode", rec.get("statusCode"))
    return LogEvent(
        ts=ts,
        ip=proxy.get("clientIp") or rec.get("clientIp") or "",
        method=proxy.get("method") or rec.get("method") or "GET",
        path=proxy.get("path") or rec.get("path") or "/",
        status=int(status or 0),
        bytes=int(proxy.get("bytes") or rec.get("bytes") or 0),
        user_agent=_first_str(proxy.get("userAgent") or rec.get("userAgent")),
        host=proxy.get("host") or rec.get("host") or "",
        source=source,
    )


def parse_cloudflare(lines: Iterable[str], source: str = "") -> Iterator["LogEvent | None"]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            yield None
            continue
        yield _cloudflare_event(rec, source) if isinstance(rec, dict) else None


def parse_vercel(lines: Iterable[str], source: str = "") -> Iterator["LogEvent | None"]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            yield None
            continue
        yield _vercel_event(rec, source) if isinstance(rec, dict) else None


PARSERS = {
    "nginx": parse_nginx,
    "apache": parse_apache,
    "cloudflare": parse_cloudflare,
    "vercel": parse_vercel,
}


# --------------------------------------------------------------------------
# file handling + format sniffing
# --------------------------------------------------------------------------
def open_log(path) -> io.TextIOBase:
    """Open a log file, transparently decompressing .gz."""
    p = Path(path)
    if p.suffix == ".gz":
        return gzip.open(p, "rt", encoding="utf-8", errors="replace")
    return open(p, "r", encoding="utf-8", errors="replace")


_CF_KEYS = {
    "EdgeStartTimestamp",
    "ClientRequestUserAgent",
    "EdgeResponseStatus",
    "ClientRequestURI",
    "ClientRequestHost",
}
_VERCEL_KEYS = {"proxy", "requestId", "deploymentId", "projectId"}


def detect_format(sample_lines: Iterable[str]) -> str | None:
    """Sniff the log format from the first handful of non-empty lines."""
    lines = [ln.strip() for ln in sample_lines if ln and ln.strip()][:25]
    if not lines:
        return None

    json_recs = []
    for ln in lines:
        if ln.startswith("{"):
            try:
                rec = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                json_recs.append(rec)

    if json_recs:
        cf_score = sum(len(_CF_KEYS & set(r)) for r in json_recs)
        vc_score = sum(len(_VERCEL_KEYS & set(r)) for r in json_recs)
        if cf_score or vc_score:
            return "cloudflare" if cf_score >= vc_score else "vercel"
        return None

    matched = [_COMBINED.match(ln) for ln in lines]
    good = [m for m in matched if m]
    if len(good) >= max(1, len(lines) // 2):
        # A leading vhost token is Apache's vhost_combined; plain is nginx.
        if sum(1 for m in good if m.group("vhost")) > len(good) // 2:
            return "apache"
        return "nginx"
    return None


def sniff_file(path) -> str | None:
    with open_log(path) as fh:
        head = [next(fh, "") for _ in range(25)]
    return detect_format(head)


def parse_file(path, fmt: str | None = None) -> ParseResult:
    """Parse one log file into a ParseResult, auto-detecting the format."""
    path = Path(path)
    fmt = fmt or sniff_file(path)
    if fmt is None:
        raise ValueError(
            "could not detect log format for %s; pass --format {%s}"
            % (path, ",".join(FORMATS))
        )
    if fmt not in PARSERS:
        raise ValueError("unknown format %r; expected one of %s" % (fmt, FORMATS))

    events: list[LogEvent] = []
    skipped = 0
    with open_log(path) as fh:
        for ev in PARSERS[fmt](fh, source=str(path)):
            if ev is None:
                skipped += 1
            else:
                events.append(ev)
    return ParseResult(events=events, parsed=len(events), skipped=skipped, fmt=fmt)
