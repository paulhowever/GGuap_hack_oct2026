import json

import numpy as np
import pytest

from app.anticheat.replay import media_path
from app.core.config import ROOT
from app.f0.base import F0Track
from app.scoring.core import score_take
from app.songs import SONG_ID, SongRepo

SONGS = ROOT / "songs"
REFS = sorted(SONGS.glob("*/reference.json"))


def test_catalog_lists_without_raising():
    assert isinstance(SongRepo(SONGS).list(), list)


@pytest.mark.skipif(not REFS, reason="no songs in catalog")
@pytest.mark.parametrize("ref_path", REFS, ids=[p.parent.name for p in REFS])
def test_catalog_song_loads_and_scores(ref_path, cfg):
    song_dir = ref_path.parent
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    assert SONG_ID.match(song_dir.name)
    assert ref["id"] == song_dir.name
    repo = SongRepo(SONGS)
    assert repo.get(ref["id"]) is not None
    assert ref["id"] in [item["id"] for item in repo.list()]
    for key in ("minus", "guide"):
        path = media_path(ref["audio"][key], SONGS)
        assert path is not None, key
        assert path.is_file(), key
    dur = ref["audio"]["duration"]
    assert dur > 0
    for key in ("first_note", "last_end", "range_midi", "difficulty"):
        assert key in ref["stats"], key
    check_path = song_dir / "check.json"
    if check_path.is_file():
        assert json.loads(check_path.read_text(encoding="utf-8"))["pass"] is True
    t = np.arange(0, dur, 0.016)
    zeros = np.zeros_like(t)
    track = F0Track(t=t, hz=zeros, conf=zeros, rms=zeros)
    result = score_take(ref, track, 0.0, cfg, "normal", None)
    assert result["score"]["total"] == 0
