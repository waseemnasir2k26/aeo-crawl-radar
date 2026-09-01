"""Optional reverse + forward DNS verification of crawler IPs.

A user-agent string is a claim. The vendors below publish crawler hostnames that
resolve in both directions, which is the check Google, Bing and Apple document
for their own crawlers:

    1. reverse-DNS the client IP    -> hostname
    2. the hostname must end with a vendor-published suffix
    3. forward-resolve that hostname and confirm the original IP is in the answer

Anything else is reported as `unverified` (no published suffix for that bot) or
`failed` (a hit claiming to be a bot from an IP that does not check out).
"""

from __future__ import annotations

import socket

VERIFIED = "verified"
FAILED = "failed"
UNCHECKED = "unchecked"
UNSUPPORTED = "unsupported"


class DNSVerifier:
    """Caches per-IP results; one lookup pair per unique IP, not per log line."""

    def __init__(self, timeout: float = 3.0):
        self.timeout = timeout
        self._cache: dict[tuple[str, tuple[str, ...]], str] = {}
        self.lookups = 0

    def _reverse(self, ip: str) -> str | None:
        try:
            socket.setdefaulttimeout(self.timeout)
            host, _, _ = socket.gethostbyaddr(ip)
            return host.lower().rstrip(".")
        except (socket.herror, socket.gaierror, OSError):
            return None

    def _forward(self, host: str) -> set[str]:
        try:
            socket.setdefaulttimeout(self.timeout)
            infos = socket.getaddrinfo(host, None)
        except (socket.gaierror, OSError):
            return set()
        return {i[4][0] for i in infos}

    def verify(self, ip: str, suffixes) -> str:
        """Return VERIFIED / FAILED / UNSUPPORTED for one IP + suffix list."""
        suffixes = tuple(suffixes or ())
        if not suffixes:
            return UNSUPPORTED
        if not ip:
            return FAILED
        key = (ip, suffixes)
        if key in self._cache:
            return self._cache[key]

        self.lookups += 1
        host = self._reverse(ip)
        result = FAILED
        if host and any(host.endswith(s.lstrip("*")) for s in suffixes):
            if ip in self._forward(host):
                result = VERIFIED
        self._cache[key] = result
        return result
