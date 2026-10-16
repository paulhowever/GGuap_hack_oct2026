import json
import shutil
import subprocess
from pathlib import Path

import pytest

from refpipe import usdx
from refpipe.cli import main
from refpipe.compile import compile_dir, compile_reference, difficulty, line_text, octave_shift
from refpipe.errors import RefpipeError
from refpipe.meta import load_meta

HEAD = ["#TITLE:T", "#ARTIST:A", "#MP3:a.mp3", "#BPM:300"]
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def test_demo_matches_contract_fixture(demo_dir, demo_fixture):
    assert compile_dir(demo_dir, duration=12.0) == demo_fixture


def test_time_formula(demo_dir):
    ref = compile_dir(demo_dir, duration=12.0)
    beat_s = 15 / ref["timing"]["bpm_txt"]
    for note in (n for line in ref["lines"] for n in line["notes"]):
        assert note["t"] == pytest.approx(ref["timing"]["gap_ms"] / 1000 + note["beat"] * beat_s, abs=5e-4)
        assert note["d"] == pytest.approx(note["len"] * beat_s, abs=5e-4)
        assert note["pc"] == note["midi"] % 12


@pytest.mark.parametrize(
    ("midis", "voice", "shift"),
    [
        ([72, 74, 76, 79, 81], "male", -24),
        ([72, 74, 76, 79, 81], "female", -12),
        ([60, 62, 64, 65, 67], "female", 0),
        ([48, 50, 52, 53, 55], "female", 12),
    ],
)
def test_octave_shift(midis, voice, shift):
    assert octave_shift(midis, voice) == shift


def test_difficulty():
    assert difficulty(7, 6, 6.4) == 1
    assert difficulty(17, 58, 26.6) == 2
    assert difficulty(17, 90, 30.0) == 3


def test_line_text_strips_tilde_and_spaces():
    text = "\n".join([*HEAD, "#GAP:0", ": 0 2 0 Ой ", ": 2 2 0 ~", ": 4 2 0  то", "E"])
    assert line_text(usdx.parse(text).lines[0]) == "Ой то"


def test_types_octave_and_golden_share(tmp_path, demo_meta_text):
    (tmp_path / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    text = "\n".join(
        [
            *HEAD,
            "#GAP:3000",
            ": 0 10 12 a ",
            "* 10 10 14 b ",
            "F 20 10 0 c ",
            "R 30 10 0 d ",
            "G 40 10 16 e",
            "E",
        ]
    )
    ref = compile_reference(usdx.parse(text), load_meta(tmp_path / "meta.yaml"), "x", 10.0)
    notes = ref["lines"][0]["notes"]
    assert [n["type"] for n in notes] == ["normal", "golden", "free", "rap", "rap_golden"]
    assert [n["midi"] for n in notes[:2]] == [60, 62]
    assert ref["stats"]["range_midi"] == [60, 62]
    assert ref["stats"]["golden_share"] == 0.4
    assert ref["audio"]["minus"] == "/media/x/minus.mp3"


def test_duration_fallback_without_minus(demo_dir):
    assert compile_dir(demo_dir)["audio"]["duration"] == pytest.approx(10.4)


def test_cli_writes_reference(demo_dir, demo_fixture, capsys):
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 0
    assert json.loads((demo_dir / "reference.json").read_text(encoding="utf-8")) == demo_fixture
    assert "demo: 6 notes" in capsys.readouterr().out


def test_cli_reports_bad_txt(demo_dir, capsys):
    (demo_dir / "song.txt").write_text("#TITLE:x\nE\n", encoding="utf-8")
    assert main(["compile", str(demo_dir)]) == 2
    assert "missing #ARTIST" in capsys.readouterr().err


def test_dot_dir_uses_folder_name(demo_dir, monkeypatch):
    monkeypatch.chdir(demo_dir)
    ref = compile_dir(Path("."), duration=12.0)
    assert ref["id"] == "demo"
    assert ref["audio"]["minus"] == "/media/demo/minus.mp3"
    assert ref["audio"]["guide"] == "/media/demo/guide.mp3"


def test_cli_dot_dir_writes_reference(demo_dir, monkeypatch, capsys):
    monkeypatch.chdir(demo_dir)
    assert main(["compile", ".", "--duration", "12"]) == 0
    ref = json.loads((demo_dir / "reference.json").read_text(encoding="utf-8"))
    assert ref["id"] == "demo"
    assert "demo: 6 notes" in capsys.readouterr().out


def test_duration_shorter_than_last_end_rejected(demo_dir):
    with pytest.raises(RefpipeError, match="shorter than the last note end 8.9"):
        compile_dir(demo_dir, duration=5.0)


def test_duration_equal_to_last_end_accepted(demo_dir):
    assert compile_dir(demo_dir, duration=8.9)["audio"]["duration"] == 8.9


def test_non_positive_duration_rejected(demo_dir):
    with pytest.raises(RefpipeError, match="must be positive"):
        compile_dir(demo_dir, duration=-3.0)


@needs_ffmpeg
def test_truncated_minus_rejected(demo_dir):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-q:a",
            "2",
            str(demo_dir / "minus.mp3"),
        ],
        check=True,
    )
    with pytest.raises(RefpipeError, match="shorter than the last note end"):
        compile_dir(demo_dir)


@pytest.mark.parametrize(
    ("duration", "message"),
    [("5", "shorter than the last note end"), ("-3", "must be positive")],
)
def test_cli_reports_bad_duration(demo_dir, capsys, duration, message):
    assert main(["compile", str(demo_dir), "--duration", duration]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert message in err
    assert not (demo_dir / "reference.json").exists()


@pytest.mark.parametrize("payload", [None, b"#TITLE:\x98\n"], ids=["missing", "undecodable"])
def test_cli_reports_unreadable_song_txt(demo_dir, capsys, payload):
    song = demo_dir / "song.txt"
    if payload is None:
        song.unlink()
    else:
        song.write_bytes(payload)
    assert main(["compile", str(demo_dir)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert "song.txt" in err
