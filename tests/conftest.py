import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def nginx_log() -> Path:
    return FIXTURES / "access.nginx.log"


@pytest.fixture
def taxonomy():
    from aeo_crawl_radar.bots import BotTaxonomy

    return BotTaxonomy.from_file()


@pytest.fixture
def db_path(tmp_path) -> Path:
    return tmp_path / "radar.sqlite"
