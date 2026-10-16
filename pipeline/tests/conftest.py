import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

DEMO_LINES = [
    "#TITLE:Демо-гамма",
    "#ARTIST:команда",
    "#LANGUAGE:Russian",
    "#MP3:minus.mp3",
    "#BPM:300",
    "#GAP:2500",
    ": 0 16 0 до ",
    ": 20 16 2 ре ",
    "* 40 20 4 ми",
    "- 60",
    ": 70 16 5 фа ",
    ": 90 16 7 соль ",
    ": 110 18 9 ля",
    "E",
]
DEMO_TXT = "\n".join(DEMO_LINES) + "\n"


@pytest.fixture
def demo_txt() -> str:
    return DEMO_TXT


@pytest.fixture
def demo_fixture() -> dict:
    return json.loads((REPO / "contracts" / "fixtures" / "demo.reference.json").read_text(encoding="utf-8"))


DEMO_META = """\
title: Демо-гамма
artist: команда
language: ru
voice: female
source:
  origin: manual
license:
  music:
    title: Демо-гамма
    author: huap team
    license: own
  recording:
    title: Демо-гамма
    author: huap team
    license: own
  attribution: huap team
vocalists: []
"""


@pytest.fixture
def demo_meta_text() -> str:
    return DEMO_META


@pytest.fixture
def demo_dir(tmp_path: Path) -> Path:
    song_dir = tmp_path / "demo"
    song_dir.mkdir()
    (song_dir / "song.txt").write_text(DEMO_TXT, encoding="utf-8")
    (song_dir / "meta.yaml").write_text(DEMO_META, encoding="utf-8")
    return song_dir
