import json

import pytest

from app.core.config import ROOT
from app.scoring.config import load_scoring_config


@pytest.fixture(scope="session")
def demo_ref() -> dict:
    return json.loads((ROOT / "contracts" / "fixtures" / "demo.reference.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def cfg():
    return load_scoring_config(ROOT / "contracts" / "scoring.json")
