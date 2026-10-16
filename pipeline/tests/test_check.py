import dataclasses
import json
import shutil
import subprocess
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from refpipe import audio, usdx
from refpipe.check import (
    build_report,
    check_dir,
    run_cases,
    run_check,
    self_score_checks,
    structural_checks,
    variants,
)
from refpipe.cli import main
from refpipe.compile import compile_reference
from refpipe.meta import load_meta

REPO = Path(__file__).resolve().parents[2]
needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)
GOOD = {"guide": 9600, "octave_up": 9590, "octave_down": 9580, "plus2": 300, "silence": 0, "delay150": 9300}


@dataclasses.dataclass(frozen=True)
class Track:
    t: np.ndarray
    hz: np.ndarray
    conf: np.ndarray
    rms: np.ndarray


class FakeEngine:
    name = "fake"
    version = "1.0"

    def track(self, audio_data, sr):
        n = 4
        return Track(t=np.arange(n) / 100, hz=np.full(n, 220.0), conf=np.ones(n), rms=np.ones(n))


def make_ref(tmp_path: Path, meta_text: str) -> dict:
    rows = ["#TITLE:T", "#ARTIST:A", "#MP3:minus.mp3", "#BPM:300", "#GAP:3000"]
    for k in range(20):
        if k and k % 5 == 0:
            rows.append(f"- {k * 10}")
        kind = "*" if k in (4, 14) else ":"
        rows.append(f"{kind} {k * 10} 8 {k % 5} la ")
    rows.append("E")
    (tmp_path / "meta.yaml").write_text(meta_text, encoding="utf-8")
    return compile_reference(usdx.parse("\n".join(rows)), load_meta(tmp_path / "meta.yaml"), "synth", 16.0)


def make_contiguous_ref(tmp_path: Path, meta_text: str, bpm: str, long_note: int | None = None) -> dict:
    rows = ["#TITLE:T", "#ARTIST:A", "#MP3:minus.mp3", f"#BPM:{bpm}", "#GAP:3000"]
    for k in range(30):
        if k and k % 10 == 0:
            rows.append(f"- {k * 6}")
        length = 7 if k == long_note else 6
        rows.append(f": {k * 6} {length} {k % 5} la ")
    rows.append("E")
    (tmp_path / "meta.yaml").write_text(meta_text, encoding="utf-8")
    return compile_reference(usdx.parse("\n".join(rows)), load_meta(tmp_path / "meta.yaml"), "synth", 40.0)


def result(total: int, notes: list[dict] | None = None) -> dict:
    return {"score": {"total": total, "max": 10000}, "notes": notes or []}


def guide_notes(count: int = 6, cents: int = 10, onset: int = 20) -> list[dict]:
    return [{"i": i, "cents": cents, "onset_ms": onset} for i in range(count)]


def results_from(totals: dict[str, int], notes: list[dict]) -> dict[str, dict]:
    return {name: result(total, notes if name == "guide" else None) for name, total in totals.items()}


def by_code(checks) -> dict:
    return {c.code: c for c in checks}


def fake_score(ref, track, wav_t0, cfg, difficulty, lag_hint_ms):
    hz = float(track.hz[0])
    if hz == 0:
        return result(0)
    if hz not in (110.0, 220.0, 440.0):
        return result(300)
    return result(9300 if wav_t0 else 9600, guide_notes(20))


def test_structural_on_demo_fixture(demo_fixture):
    checks = by_code(structural_checks(demo_fixture))
    assert checks["no_overlap"].ok and checks["min_note_len"].ok and checks["range"].ok
    assert checks["lead_in"].ok and checks["tail"].value == 3.1
    assert not checks["golden_share"].ok and checks["golden_share"].value == 0.167
    assert not checks["fragment_len"].ok and checks["fragment_len"].level == "warn"


def test_structural_detects_overlap_short_and_range(demo_fixture):
    ref = json.loads(json.dumps(demo_fixture))
    ref["lines"][0]["notes"][0]["len"] = 24
    ref["lines"][1]["notes"][0]["d"] = 0.05
    ref["lines"][1]["notes"][1]["midi"] = 90
    checks = by_code(structural_checks(ref))
    assert checks["no_overlap"].value == 1
    assert checks["min_note_len"].value == 1
    assert not checks["range"].ok


@pytest.mark.parametrize("bpm", ["120.5", "187.3", "233.4"])
def test_touching_notes_do_not_overlap(tmp_path, demo_meta_text, bpm):
    ref = make_contiguous_ref(tmp_path, demo_meta_text, bpm)
    notes = [n for line in ref["lines"] for n in line["notes"]]
    assert all(a["beat"] + a["len"] == b["beat"] for a, b in pairwise(notes))
    checks = by_code(structural_checks(ref))
    assert checks["no_overlap"].ok and checks["no_overlap"].value == 0


@pytest.mark.parametrize("bpm", ["120.5", "187.3", "233.4"])
def test_one_beat_overlap_is_detected(tmp_path, demo_meta_text, bpm):
    ref = make_contiguous_ref(tmp_path, demo_meta_text, bpm, long_note=4)
    checks = by_code(structural_checks(ref))
    assert not checks["no_overlap"].ok and checks["no_overlap"].value == 1


def test_variants_transform_track():
    track = Track(t=np.array([0.0, 0.01]), hz=np.array([220.0, 0.0]), conf=np.ones(2), rms=np.ones(2))
    cases = variants(track)
    assert cases["octave_up"][0].hz.tolist() == [440.0, 0.0]
    assert cases["octave_down"][0].hz.tolist() == [110.0, 0.0]
    assert cases["plus2"][0].hz[0] == pytest.approx(220.0 * 2 ** (2 / 12))
    assert not cases["silence"][0].hz.any() and not cases["silence"][0].rms.any()
    assert cases["delay150"][0] is track and cases["delay150"][1] == 0.15
    assert cases["guide"][1] == 0.0


def test_run_cases_passes_arguments(demo_fixture):
    calls = []

    def spy(ref, track, wav_t0, cfg, difficulty, lag_hint_ms):
        calls.append((wav_t0, cfg, difficulty, lag_hint_ms))
        return result(1)

    track = Track(t=np.zeros(1), hz=np.full(1, 220.0), conf=np.ones(1), rms=np.ones(1))
    out = run_cases(demo_fixture, track, "cfg", spy)
    assert list(out) == ["guide", "octave_up", "octave_down", "plus2", "silence", "delay150"]
    assert {c[1:] for c in calls} == {("cfg", "normal", 0.0)}
    assert [c[0] for c in calls] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.15]


def test_self_score_all_pass(demo_fixture):
    assert all(c.ok for c in self_score_checks(demo_fixture, results_from(GOOD, guide_notes())))


@pytest.mark.parametrize(
    ("case", "total", "code"),
    [
        ("guide", 8900, "score_guide"),
        ("octave_up", 9300, "score_octave"),
        ("octave_down", 9750, "score_octave"),
        ("plus2", 4100, "score_plus2"),
        ("silence", 15, "score_silence"),
        ("delay150", 8400, "score_delay150"),
    ],
)
def test_self_score_failures(demo_fixture, case, total, code):
    checks = by_code(
        self_score_checks(demo_fixture, results_from(dict(GOOD, **{case: total}), guide_notes()))
    )
    assert not checks[code].ok


def test_pitch_class_and_onset(demo_fixture):
    off_key = guide_notes()
    off_key[3] = {"i": 3, "cents": 140, "onset_ms": 20}
    checks = by_code(self_score_checks(demo_fixture, results_from(GOOD, off_key)))
    assert checks["guide_pitch_class"].value == 0.833 and not checks["guide_pitch_class"].ok
    late = by_code(self_score_checks(demo_fixture, results_from(GOOD, guide_notes(onset=-120))))
    assert late["guide_onset"].value == 120 and not late["guide_onset"].ok
    unvoiced = [{"i": i, "cents": None, "onset_ms": None} for i in range(6)]
    silent = by_code(self_score_checks(demo_fixture, results_from(GOOD, unvoiced)))
    assert not silent["guide_pitch_class"].ok and not silent["guide_onset"].ok


def test_run_check_passes_with_fake_engine(tmp_path, demo_meta_text):
    ref = make_ref(tmp_path, demo_meta_text)
    report = run_check(ref, np.zeros(16000, dtype=np.float32), 16000, None, FakeEngine(), fake_score)
    assert report["pass"], report["checks"]
    assert report["engine"] == "fake-1.0"
    assert report["scores"] == {
        "guide": 9600,
        "octave_up": 9600,
        "octave_down": 9600,
        "plus2": 300,
        "silence": 0,
        "delay150": 9300,
    }
    assert {c["code"] for c in report["checks"]} >= {"golden_share", "score_delay150", "guide_onset"}


def test_run_check_without_guide(demo_fixture):
    report = run_check(demo_fixture, None, 16000, None, None, None)
    assert report["pass"] is False
    assert report["engine"] is None and report["scores"] is None
    assert report["checks"][-1]["code"] == "guide_present"


def test_cli_check_without_guide(demo_dir, capsys):
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 0
    assert main(["check", str(demo_dir)]) == 1
    report = json.loads((demo_dir / "check.json").read_text(encoding="utf-8"))
    assert report["song_id"] == "demo" and report["pass"] is False
    out = capsys.readouterr().out
    assert "FAIL golden_share" in out and "demo: FAIL" in out


def test_cli_check_needs_reference(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == 2
    assert "reference.json" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"{broken", "reference.json"),
        (b"\xff\xfe", "reference.json"),
        (b"[]", "reference.json"),
        (b'{"lines": []}', "no notes"),
        (b'{"lines": [{"notes": []}]}', "no notes"),
    ],
)
def test_cli_check_rejects_malformed_reference(tmp_path, capsys, content, message):
    (tmp_path / "reference.json").write_bytes(content)
    assert main(["check", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert message in err
    assert not (tmp_path / "check.json").exists()


def test_decode_argv(tmp_path):
    assert audio.decode_argv(tmp_path / "g.mp3", 16000) == [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(tmp_path / "g.mp3"),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "f32le",
        "-",
    ]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_load_audio(tmp_path):
    wav = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-ar",
            "44100",
            str(wav),
        ],
        check=True,
    )
    data = audio.load_audio(wav, 16000)
    assert data.dtype == np.float32
    assert abs(len(data) - 16000) < 200


@pytest.mark.integration
def test_synth_guide_passes_self_score(tmp_path, demo_meta_text):
    core = pytest.importorskip("app.scoring.core")
    synth = pytest.importorskip("app.scoring.synth")
    from app.f0 import get_engine
    from app.scoring.config import load_scoring_config

    ref = make_ref(tmp_path, demo_meta_text)
    cfg = load_scoring_config(REPO / "contracts" / "scoring.json")
    report = run_check(
        ref, synth.synth_take(ref, sr=16000), 16000, cfg, get_engine("swiftf0"), core.score_take
    )
    assert report["pass"], report["checks"]


@pytest.mark.integration
def test_detuned_guide_fails_self_score(tmp_path, demo_meta_text):
    core = pytest.importorskip("app.scoring.core")
    synth = pytest.importorskip("app.scoring.synth")
    from app.f0 import get_engine
    from app.scoring.config import load_scoring_config

    ref = make_ref(tmp_path, demo_meta_text)
    cfg = load_scoring_config(REPO / "contracts" / "scoring.json")
    guide = synth.synth_take(ref, sr=16000, cents=150.0)
    report = run_check(ref, guide, 16000, cfg, get_engine("swiftf0"), core.score_take)
    checks = {c["code"]: c for c in report["checks"]}
    assert not checks["score_guide"]["ok"]
    assert not checks["guide_pitch_class"]["ok"]
    assert report["pass"] is False


def song_rows(title: str = "T", artist: str = "A", gap: int = 3000, syl: str = "la ") -> list[str]:
    rows = [f"#TITLE:{title}", f"#ARTIST:{artist}", "#MP3:minus.mp3", "#BPM:300", f"#GAP:{gap}"]
    for k in range(20):
        if k and k % 5 == 0:
            rows.append(f"- {k * 10}")
        kind = "*" if k in (4, 14) else ":"
        rows.append(f"{kind} {k * 10} 8 {k % 5} {syl}")
    rows.append("E")
    return rows


def make_song_dir(tmp_path: Path, meta_text: str, rows: list[str], name: str = "synth") -> Path:
    song_dir = tmp_path / name
    song_dir.mkdir()
    (song_dir / "song.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (song_dir / "meta.yaml").write_text(meta_text, encoding="utf-8")
    assert main(["compile", str(song_dir), "--duration", "16"]) == 0
    return song_dir


@pytest.fixture
def fake_backend(monkeypatch):
    import app.f0
    import app.scoring.core

    monkeypatch.setattr(audio, "load_audio", lambda path, sr: np.zeros(sr, dtype=np.float32))
    monkeypatch.setattr(app.f0, "get_engine", lambda name: FakeEngine())
    monkeypatch.setattr(app.scoring.core, "score_take", fake_score)


def test_missing_minus_fails(tmp_path, demo_meta_text, fake_backend):
    song_dir = make_song_dir(tmp_path, demo_meta_text, song_rows("Демо-гамма", "команда"))
    (song_dir / "guide.mp3").write_bytes(b"\0" * 2048)
    report = check_dir(song_dir)
    checks = {c["code"]: c for c in report["checks"]}
    assert checks["minus_present"]["ok"] is False and checks["minus_present"]["level"] == "error"
    assert report["pass"] is False
    (song_dir / "minus.mp3").write_bytes(b"\0" * 2048)
    report = check_dir(song_dir)
    checks = {c["code"]: c for c in report["checks"]}
    assert checks["minus_present"]["ok"] and checks["media_size"]["ok"] and checks["media_size"]["value"] == 2
    assert checks["reference_fresh"]["ok"] and checks["meta_matches_txt"]["ok"]
    assert report["pass"], report["checks"]


def test_large_media_warns(tmp_path, demo_meta_text, fake_backend):
    song_dir = make_song_dir(tmp_path, demo_meta_text, song_rows("Демо-гамма", "команда"))
    (song_dir / "guide.mp3").write_bytes(b"\0" * 2048)
    (song_dir / "minus.mp3").write_bytes(b"\0" * (1536 * 1024))
    report = check_dir(song_dir)
    size = {c["code"]: c for c in report["checks"]}["media_size"]
    assert (size["ok"], size["value"], size["level"]) == (False, 1536, "warn")
    assert report["pass"]


def test_stale_reference_warns(tmp_path, demo_meta_text, fake_backend):
    song_dir = make_song_dir(tmp_path, demo_meta_text, song_rows("Демо-гамма", "команда"))
    (song_dir / "guide.mp3").write_bytes(b"\0" * 2048)
    (song_dir / "minus.mp3").write_bytes(b"\0" * 2048)
    assert {c["code"]: c for c in check_dir(song_dir)["checks"]}["reference_fresh"]["ok"]
    txt = song_dir / "song.txt"
    txt.write_text(txt.read_text(encoding="utf-8").replace("#GAP:3000", "#GAP:3100"), encoding="utf-8")
    report = check_dir(song_dir)
    fresh = {c["code"]: c for c in report["checks"]}["reference_fresh"]
    assert (fresh["ok"], fresh["level"]) == (False, "warn")
    assert report["pass"]


def test_unreadable_sources_mark_reference_stale(tmp_path, demo_meta_text, fake_backend):
    song_dir = make_song_dir(tmp_path, demo_meta_text, song_rows("Демо-гамма", "команда"))
    (song_dir / "meta.yaml").unlink()
    checks = {c["code"]: c for c in check_dir(song_dir)["checks"]}
    assert checks["reference_fresh"]["ok"] is False
    assert checks["meta_matches_txt"]["ok"]


def test_meta_title_mismatch_warns(tmp_path, fake_backend):
    meta = (REPO / "pipeline" / "examples" / "meta.example.yaml").read_text(encoding="utf-8")
    song_dir = make_song_dir(tmp_path, meta, song_rows("Коробейники", "нар."), name="korobeiniki")
    (song_dir / "guide.mp3").write_bytes(b"\0" * 2048)
    (song_dir / "minus.mp3").write_bytes(b"\0" * 2048)
    report = check_dir(song_dir)
    match = {c["code"]: c for c in report["checks"]}["meta_matches_txt"]
    assert (match["ok"], match["level"]) == (False, "warn")
    assert report["pass"], report["checks"]


def test_word_breaks_warns(tmp_path, demo_meta_text):
    rows = ["#TITLE:T", "#ARTIST:A", "#MP3:minus.mp3", "#BPM:300", "#GAP:3000"]
    rows += [f": {k * 10} 8 {k % 5} la" for k in range(6)]
    rows += ["- 60", *[f": {60 + k * 10} 8 0 la " for k in range(6)], "E"]
    (tmp_path / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    ref = compile_reference(usdx.parse("\n".join(rows)), load_meta(tmp_path / "meta.yaml"), "x", 12.0)
    breaks = by_code(structural_checks(ref))["word_breaks"]
    assert (breaks.ok, breaks.value, breaks.level) == (False, 1, "warn")


def test_word_breaks_ok_on_spaced_lines(tmp_path, demo_meta_text):
    assert by_code(structural_checks(make_ref(tmp_path, demo_meta_text)))["word_breaks"].ok


def test_guide_lag_warns(demo_fixture):
    results = results_from(GOOD, guide_notes())
    base = self_score_checks(demo_fixture, results)
    assert "guide_lag" not in by_code(base)
    results["guide"]["latency"] = {"estimated_ms": 300.0}
    checks = self_score_checks(demo_fixture, results)
    lag = by_code(checks)["guide_lag"]
    assert (lag.ok, lag.value, lag.level) == (False, 300, "warn")
    assert build_report(demo_fixture, checks)["pass"] == build_report(demo_fixture, base)["pass"]
    results["guide"]["latency"] = {"estimated_ms": -40.0}
    assert by_code(self_score_checks(demo_fixture, results))["guide_lag"].ok


def test_guide_onset_found_warns(demo_fixture):
    notes = [{"i": i, "cents": 10, "onset_ms": 20 if i == 0 else None} for i in range(6)]
    checks = self_score_checks(demo_fixture, results_from(GOOD, notes))
    found = by_code(checks)["guide_onset_found"]
    assert (found.ok, found.value, found.level) == (False, 0.167, "warn")
    assert by_code(checks)["guide_onset"].ok
    base = self_score_checks(demo_fixture, results_from(GOOD, guide_notes()))
    assert by_code(base)["guide_onset_found"].ok
    assert build_report(demo_fixture, checks)["pass"] == build_report(demo_fixture, base)["pass"]


def write_e2e_source(tmp_path: Path, meta_text: str, delay_s: float) -> Path:
    synth = pytest.importorskip("app.scoring.synth")
    src = tmp_path / "src"
    src.mkdir()
    (src / "song.txt").write_text("\n".join(song_rows("Демо-гамма", "команда", gap=6000)) + "\n", "utf-8")
    (src / "meta.yaml").write_text(meta_text, encoding="utf-8")
    uncut = compile_reference(usdx.read(src / "song.txt"), load_meta(src / "meta.yaml"), "src", 20.0)
    sf.write(src / "guide.wav", synth.synth_take(uncut, sr=16000, delay_s=delay_s), 16000, subtype="PCM_16")
    t = np.arange(20 * 44100) / 44100
    sf.write(src / "minus.wav", (0.05 * np.sin(2 * np.pi * 110 * t)).astype(np.float32), 44100)
    return src


def run_e2e(tmp_path: Path, meta_text: str, delay_s: float) -> tuple[int, dict]:
    src = write_e2e_source(tmp_path, meta_text, delay_s)
    out = tmp_path / "songs" / "e2e"
    out.mkdir(parents=True)
    (out / "meta.yaml").write_text(meta_text, encoding="utf-8")
    cut = ["cut", str(src / "song.txt"), "--t0", "3.4", "--t1", "18", "--out", str(out)]
    assert main([*cut, "--minus", str(src / "minus.wav"), "--guide", str(src / "guide.wav")]) == 0
    assert main(["compile", str(out)]) == 0
    code = main(["check", str(out)])
    return code, json.loads((out / "check.json").read_text(encoding="utf-8"))


@pytest.mark.integration
@needs_ffmpeg
def test_e2e_cut_compile_check(tmp_path, demo_meta_text):
    code, report = run_e2e(tmp_path, demo_meta_text, 0.0)
    checks = {c["code"]: c for c in report["checks"]}
    assert code == 0 and report["pass"], report["checks"]
    assert checks["guide_lag"]["ok"], checks["guide_lag"]
    assert checks["minus_present"]["ok"] and checks["reference_fresh"]["ok"]
    assert checks["meta_matches_txt"]["ok"]


@pytest.mark.integration
@needs_ffmpeg
def test_e2e_late_guide_passes_with_lag_warning(tmp_path, demo_meta_text):
    code, report = run_e2e(tmp_path, demo_meta_text, 0.3)
    checks = {c["code"]: c for c in report["checks"]}
    assert code == 0 and report["pass"], report["checks"]
    assert not checks["guide_lag"]["ok"] and checks["guide_lag"]["level"] == "warn"
