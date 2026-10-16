import json
import shutil
import subprocess

import numpy as np
import pytest

from refpipe import audio, usdx
from refpipe.cli import build_parser, main
from refpipe.cut import cut_song, fragment_warnings
from refpipe.errors import CutError
from refpipe.meta import load_meta

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def phrase_song(lines: int = 4) -> usdx.UsdxSong:
    rows = [
        "#TITLE:T",
        "#ARTIST:A",
        "#MP3:full.wav",
        "#VIDEO:clip.mp4",
        "#LANGUAGE:Russian",
        "#BPM:300",
        "#GAP:5000",
    ]
    for k in range(lines):
        if k:
            rows.append(f"- {50 * k - 10}")
        rows += [f": {50 * k + 10 * j} 8 {j} la " for j in range(4)]
    rows.append("E")
    return usdx.parse("\n".join(rows))


def test_cut_demo_second_line(demo_txt):
    song = usdx.parse(demo_txt)
    result = cut_song(song, 3.0, 10.4)
    cut = result.song
    assert cut.gap_ms == 3000.0
    assert [n.beat for n in cut.notes] == [0, 20, 40]
    assert len(cut.lines) == 1 and cut.lines[0].break_beat is None
    assert (cut.audio, cut.extra) == ("minus.mp3", {"LANGUAGE": "Russian", "VOCALS": "guide.mp3"})


def test_cut_keeps_whole_phrases_and_times():
    song = phrase_song()
    result = cut_song(song, 2.0, 11.0)
    cut = result.song
    assert cut.gap_ms == 3000.0
    assert [len(line.notes) for line in cut.lines] == [4, 4]
    assert [line.break_beat for line in cut.lines] == [40, None]
    for old, new in zip(song.notes[:8], cut.notes, strict=True):
        assert cut.note_t(new) + 2.0 == pytest.approx(song.note_t(old))
    assert cut.note_t(cut.notes[0]) >= 2.5
    assert (11.0 - 2.0) - cut.note_end_t(cut.notes[-1]) >= 1.5 - 1e-9


def test_partial_phrases_are_dropped():
    cut = cut_song(phrase_song(), 3.0, 13.0).song
    assert len(cut.lines) == 1
    assert cut.gap_ms == 2500 + 2000.0


def test_no_phrase_fits():
    with pytest.raises(CutError, match="no whole phrase"):
        cut_song(phrase_song(), 4.0, 8.0)


def test_t1_must_follow_t0():
    with pytest.raises(CutError, match="greater"):
        cut_song(phrase_song(), 5.0, 5.0)


def test_warnings():
    assert fragment_warnings(31.0, 58) == ()
    assert fragment_warnings(7.4, 3) == (
        "fragment is 7.4 s, expected 20-40 s",
        "fragment has 3 notes, expected 40-120",
    )


def test_ffmpeg_cut_argv(tmp_path):
    assert audio.ffmpeg_cut_argv(tmp_path / "no_vocals.wav", tmp_path / "minus.mp3", 61.2, 92.2) == [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        "61.200",
        "-t",
        "31.000",
        "-i",
        str(tmp_path / "no_vocals.wav"),
        "-af",
        "afade=t=in:d=0.3,afade=t=out:st=30.000:d=1",
        "-ar",
        "44100",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(tmp_path / "minus.mp3"),
    ]


@needs_ffmpeg
def test_ffmpeg_cut_keeps_middle_audible(tmp_path):
    src = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=10",
            "-ar",
            "44100",
            str(src),
        ],
        check=True,
    )
    dst = tmp_path / "cut.mp3"
    audio.run_tool(audio.ffmpeg_cut_argv(src, dst, 3.0, 8.0))
    assert audio.probe_duration(dst) == pytest.approx(5.0, abs=0.1)
    rate = 44100
    pcm = np.frombuffer(
        audio.capture_tool(["ffmpeg", "-v", "error", "-i", str(dst), "-f", "s16le", "-ac", "1", "-"]),
        dtype=np.int16,
    ).astype(float)

    def rms(start_s: float, end_s: float) -> float:
        return float(np.sqrt(np.mean(pcm[int(start_s * rate) : int(end_s * rate)] ** 2)))

    middle = rms(2.0, 3.0)
    assert middle > 1000
    assert rms(4.9, 5.0) < 0.1 * middle


def test_cli_cut(tmp_path, monkeypatch, capsys, demo_txt, demo_meta_text):
    calls = []
    monkeypatch.setattr(audio, "run_tool", lambda argv: calls.append(argv))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nv.wav").write_bytes(b"")
    (tmp_path / "v.wav").write_bytes(b"")
    src = tmp_path / "full.txt"
    src.write_text(demo_txt, encoding="utf-8")
    out = tmp_path / "songs" / "demo"
    out.mkdir(parents=True)
    (out / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    argv = [
        "cut",
        str(src),
        "--t0",
        "3",
        "--t1",
        "10.4",
        "--out",
        str(out),
        "--minus",
        "nv.wav",
        "--guide",
        "v.wav",
    ]
    assert main(argv) == 0
    assert [call[-1] for call in calls] == [str(out / "minus.mp3"), str(out / "guide.mp3")]
    assert [call[call.index("-i") + 1] for call in calls] == ["nv.wav", "v.wav"]
    assert usdx.read(out / "song.txt").gap_ms == 3000.0
    assert load_meta(out / "meta.yaml").source.t0_ms == 3000
    assert "warning: fragment is 7.4 s" in capsys.readouterr().err


def test_break_beats_shift_by_first_beat():
    cut = cut_song(phrase_song(), 3.0, 17.0).song
    assert [len(line.notes) for line in cut.lines] == [4, 4, 4]
    assert cut.notes[0].beat == 0
    assert [line.break_beat for line in cut.lines] == [40, 90, None]
    assert cut.gap_ms == 4500.0


def test_cli_cut_missing_source_writes_nothing(tmp_path, monkeypatch, capsys, demo_txt, demo_meta_text):
    calls = []
    monkeypatch.setattr(audio, "run_tool", lambda argv: calls.append(argv))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nv.wav").write_bytes(b"")
    src = tmp_path / "full.txt"
    src.write_text(demo_txt, encoding="utf-8")
    out = tmp_path / "songs" / "demo"
    out.mkdir(parents=True)
    (out / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    (out / "song.txt").write_text("old\n", encoding="utf-8")
    argv = [
        "cut",
        str(src),
        "--t0",
        "3",
        "--t1",
        "10.4",
        "--out",
        str(out),
        "--minus",
        "nv.wav",
        "--guide",
        "missing.wav",
    ]
    assert main(argv) == 2
    assert "missing.wav" in capsys.readouterr().err
    assert calls == []
    assert (out / "song.txt").read_text(encoding="utf-8") == "old\n"
    assert load_meta(out / "meta.yaml").source.t0_ms == 0


def test_cli_cut_bad_meta_writes_nothing(tmp_path, monkeypatch, demo_txt):
    calls = []
    monkeypatch.setattr(audio, "run_tool", lambda argv: calls.append(argv))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nv.wav").write_bytes(b"")
    src = tmp_path / "full.txt"
    src.write_text(demo_txt, encoding="utf-8")
    out = tmp_path / "songs" / "demo"
    out.mkdir(parents=True)
    (out / "meta.yaml").write_text("title: x\n", encoding="utf-8")
    argv = [
        "cut",
        str(src),
        "--t0",
        "3",
        "--t1",
        "10.4",
        "--out",
        str(out),
        "--minus",
        "nv.wav",
    ]
    assert main(argv) == 2
    assert calls == []
    assert not (out / "song.txt").exists()


def run_cli_cut(tmp_path, monkeypatch, demo_txt, demo_meta_text, *flags):
    calls = []
    monkeypatch.setattr(audio, "run_tool", lambda argv: calls.append(argv))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nv.wav").write_bytes(b"")
    (tmp_path / "v.wav").write_bytes(b"")
    src = tmp_path / "full.txt"
    src.write_text(demo_txt, encoding="utf-8")
    out = tmp_path / "songs" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    if not (out / "meta.yaml").exists():
        (out / "meta.yaml").write_text(demo_meta_text, encoding="utf-8")
    argv = ["cut", str(src), "--out", str(out), "--minus", "nv.wav", "--guide", "v.wav", *flags]
    return main(argv), calls, out


def seek(call: list[str]) -> tuple[float, float]:
    return float(call[call.index("-ss") + 1]), float(call[call.index("-t") + 1])


def test_cli_cut_guide_offset(tmp_path, monkeypatch, demo_txt, demo_meta_text):
    flags = ("--t0", "3", "--t1", "10.4", "--guide-offset-ms", "1200")
    code, calls, out = run_cli_cut(tmp_path, monkeypatch, demo_txt, demo_meta_text, *flags)
    assert code == 0
    minus, guide = calls
    assert minus[-1] == str(out / "minus.mp3") and guide[-1] == str(out / "guide.mp3")
    assert seek(minus) == pytest.approx((3.0, 7.4))
    assert seek(guide) == pytest.approx((4.2, 7.4))
    assert usdx.read(out / "song.txt").gap_ms == 3000.0
    assert load_meta(out / "meta.yaml").source.t0_ms == 3000


def test_cli_cut_negative_guide_start_is_rejected(tmp_path, monkeypatch, capsys, demo_txt, demo_meta_text):
    calls = []
    monkeypatch.setattr(audio, "run_tool", lambda argv: calls.append(argv))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nv.wav").write_bytes(b"")
    (tmp_path / "v.wav").write_bytes(b"")
    src = tmp_path / "full.txt"
    src.write_text(demo_txt, encoding="utf-8")
    out = tmp_path / "out"
    argv = ["cut", str(src), "--t0", "0.5", "--t1", "10.4", "--out", str(out), "--guide", "v.wav"]
    args = build_parser().parse_args([*argv, "--guide-offset-ms", "-1000"])
    with pytest.raises(CutError, match="guide"):
        args.func(args)
    assert main([*argv, "--guide-offset-ms", "-1000"]) == 2
    assert "guide-offset-ms" in capsys.readouterr().err
    assert calls == []
    assert not out.exists()


def test_negative_t0_is_rejected():
    with pytest.raises(CutError, match="t0 must be >= 0"):
        cut_song(phrase_song(), -1, 33)


def test_dropped_opening_phrase_is_reported():
    rows = ["#TITLE:T", "#ARTIST:A", "#MP3:full.wav", "#BPM:300", "#GAP:2000"]
    for k in range(4):
        if k:
            rows.append(f"- {50 * k - 10}")
        rows += [f": {50 * k + 10 * j} 8 {j} la " for j in range(4)]
    rows.append("E")
    result = cut_song(usdx.parse("\n".join(rows)), 0, 11)
    assert [len(line.notes) for line in result.song.lines] == [4, 4]
    dropped = [w for w in result.warnings if w.startswith("phrase ")]
    assert dropped[0] == "phrase 1 (2.0–3.9 s) dropped: needs 2.5 s lead-in and 1.5 s tail inside [0, 11]"
    assert [w.split(" (")[0] for w in dropped] == ["phrase 1", "phrase 4"]


def test_only_phrases_overlapping_window_are_reported():
    result = cut_song(phrase_song(), 2.0, 11.0)
    assert [w.split(" (")[0] for w in result.warnings if w.startswith("phrase ")] == ["phrase 3"]


def test_cli_cut_marks_existing_check_stale(tmp_path, monkeypatch, demo_txt, demo_meta_text):
    out = tmp_path / "songs" / "demo"
    out.mkdir(parents=True)
    (out / "reference.json").write_text("{}\n", encoding="utf-8")
    (out / "check.json").write_text('{"pass": true}\n', encoding="utf-8")
    code, _, out = run_cli_cut(tmp_path, monkeypatch, demo_txt, demo_meta_text, "--t0", "3", "--t1", "10.4")
    assert code == 0
    assert json.loads((out / "check.json").read_text(encoding="utf-8")) == {
        "schema": 1,
        "song_id": "demo",
        "pass": False,
        "stale": "rerun refpipe compile and check",
    }


def test_cli_cut_without_reference_writes_no_check(tmp_path, monkeypatch, demo_txt, demo_meta_text):
    code, _, out = run_cli_cut(tmp_path, monkeypatch, demo_txt, demo_meta_text, "--t0", "3", "--t1", "10.4")
    assert code == 0
    assert not (out / "check.json").exists()
