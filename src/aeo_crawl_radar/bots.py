"""Bot taxonomy loading and user-agent matching."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

DEFAULT_BOTS_PATH = Path(__file__).with_name("data") / "bots.yaml"


@dataclass(frozen=True)
class Bot:
    name: str
    vendor: str
    ua_regex: str
    purpose: str
    docs: str = ""
    ai: bool = True
    verify_dns: tuple[str, ...] = field(default_factory=tuple)

    @property
    def pattern(self) -> re.Pattern[str]:
        return re.compile(self.ua_regex, re.IGNORECASE)


class BotTaxonomy:
    """A compiled set of bot definitions matched against user-agent strings."""

    def __init__(self, bots: Iterable[Bot]):
        self.bots: list[Bot] = list(bots)
        self._compiled = [(b, b.pattern) for b in self.bots]
        self._cache: dict[str, Bot | None] = {}

    # ---- construction -------------------------------------------------
    @classmethod
    def from_file(cls, path: str | Path | None = None) -> "BotTaxonomy":
        p = Path(path) if path else DEFAULT_BOTS_PATH
        with open(p, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict) -> "BotTaxonomy":
        bots: list[Bot] = []
        for key, default_ai in (("bots", True), ("reference_bots", False)):
            for entry in raw.get(key) or []:
                bots.append(
                    Bot(
                        name=entry["name"],
                        vendor=entry.get("vendor", "unknown"),
                        ua_regex=entry["ua_regex"],
                        purpose=entry.get("purpose", "unknown"),
                        docs=entry.get("docs", ""),
                        ai=bool(entry.get("ai", default_ai)),
                        verify_dns=tuple(entry.get("verify_dns") or ()),
                    )
                )
        if not bots:
            raise ValueError("bot taxonomy file contains no bots")
        # Validate every regex up-front so a typo fails loudly, not silently.
        for b in bots:
            re.compile(b.ua_regex)
        return cls(bots)

    # ---- matching -----------------------------------------------------
    def match(self, user_agent: str | None) -> Bot | None:
        """Return the first bot whose regex is found in the user-agent."""
        if not user_agent:
            return None
        if user_agent in self._cache:
            return self._cache[user_agent]
        hit: Bot | None = None
        for bot, pattern in self._compiled:
            if pattern.search(user_agent):
                hit = bot
                break
        if len(self._cache) < 50_000:
            self._cache[user_agent] = hit
        return hit

    def get(self, name: str) -> Bot | None:
        for b in self.bots:
            if b.name.lower() == name.lower():
                return b
        return None

    @property
    def ai_bots(self) -> list[Bot]:
        return [b for b in self.bots if b.ai]
