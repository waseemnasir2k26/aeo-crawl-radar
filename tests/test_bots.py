import pytest

from aeo_crawl_radar.bots import BotTaxonomy
from aeo_crawl_radar.parsers import parse_file

CASES = [
    ("Mozilla/5.0 (compatible; GPTBot/1.2; +https://openai.com/gptbot)", "GPTBot", "training"),
    ("Mozilla/5.0 (compatible; OAI-SearchBot/1.0)", "OAI-SearchBot", "search-index"),
    ("Mozilla/5.0 (compatible; ChatGPT-User/1.0)", "ChatGPT-User", "live-fetch"),
    ("Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)", "ClaudeBot", "training"),
    ("Mozilla/5.0 (compatible; Claude-User/1.0)", "Claude-User", "live-fetch"),
    ("Mozilla/5.0 (compatible; PerplexityBot/1.0)", "PerplexityBot", "search-index"),
    ("Mozilla/5.0 (compatible; Google-Extended/1.0)", "Google-Extended", "training"),
    ("Mozilla/5.0 (compatible; Bytespider;)", "Bytespider", "training"),
    ("Mozilla/5.0 (compatible; Amazonbot/0.1)", "Amazonbot", "search-index"),
    ("meta-externalagent/1.1", "meta-externalagent", "training"),
    ("CCBot/2.0 (https://commoncrawl.org/faq/)", "CCBot", "training"),
]


@pytest.mark.parametrize("ua,name,purpose", CASES)
def test_known_bots_match(taxonomy, ua, name, purpose):
    bot = taxonomy.match(ua)
    assert bot is not None and bot.name == name
    assert bot.purpose == purpose
    assert bot.ai is True


def test_humans_do_not_match(taxonomy):
    human = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )
    assert taxonomy.match(human) is None
    assert taxonomy.match("") is None
    assert taxonomy.match(None) is None


def test_reference_bots_are_not_ai(taxonomy):
    gb = taxonomy.match("Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert gb.name == "Googlebot" and gb.ai is False
    bing = taxonomy.match("Mozilla/5.0 (compatible; bingbot/2.0)")
    assert bing.name == "Bingbot" and bing.ai is False


def test_google_extended_not_confused_with_googlebot(taxonomy):
    assert taxonomy.match("Google-Extended/1.0").name == "Google-Extended"
    assert taxonomy.match("Googlebot/2.1").name == "Googlebot"


def test_applebot_extended_wins_over_applebot(taxonomy):
    assert taxonomy.match("Applebot-Extended/1.0").name == "Applebot-Extended"
    assert taxonomy.match("Applebot/0.1").name == "Applebot"


def test_matching_is_case_insensitive(taxonomy):
    assert taxonomy.match("mozilla/5.0 (compatible; gptbot/1.2)").name == "GPTBot"


def test_custom_taxonomy_overrides_defaults(tmp_path):
    custom = tmp_path / "bots.yaml"
    custom.write_text(
        "bots:\n"
        "  - name: HouseBot\n"
        "    vendor: Acme\n"
        "    ua_regex: 'HouseBot'\n"
        "    purpose: training\n"
        "    docs: https://example.test/housebot\n",
        encoding="utf-8",
    )
    tax = BotTaxonomy.from_file(custom)
    assert len(tax.bots) == 1
    assert tax.match("HouseBot/1.0").vendor == "Acme"
    assert tax.match("Mozilla/5.0 (compatible; GPTBot/1.2)") is None


def test_empty_taxonomy_rejected(tmp_path):
    empty = tmp_path / "empty.yaml"
    empty.write_text("bots: []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        BotTaxonomy.from_file(empty)


def test_every_default_bot_has_docs_and_purpose(taxonomy):
    for b in taxonomy.bots:
        assert b.docs.startswith("http"), b.name
        assert b.purpose in {"training", "search-index", "live-fetch"}, b.name


def test_fixture_traffic_classifies_as_expected(taxonomy, nginx_log):
    res = parse_file(nginx_log)
    counts = {}
    humans = 0
    for e in res.events:
        bot = taxonomy.match(e.user_agent)
        if bot is None:
            humans += 1
        else:
            counts[bot.name] = counts.get(bot.name, 0) + 1
    assert humans == 160
    assert counts["GPTBot"] == 86
    assert counts["ClaudeBot"] == 61
    assert counts["Googlebot"] == 70
    ai_hits = sum(v for k, v in counts.items() if taxonomy.get(k).ai)
    assert ai_hits == 388
