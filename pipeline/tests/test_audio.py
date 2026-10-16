import shutil
import subprocess

import pytest

from refpipe import audio
from refpipe.cli import main
from refpipe.errors import RefpipeError

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def test_ffprobe_argv(tmp_path):
    assert audio.ffprobe_argv(tmp_path / "a.mp3") == [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(tmp_path / "a.mp3"),
    ]


def test_run_tool_reports_missing_binary():
    with pytest.raises(RefpipeError, match="not found"):
        audio.run_tool(["refpipe-no-such-binary"])


@needs_ffmpeg
def test_probe_duration(tmp_path):
    wav = tmp_path / "tone.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-ar",
            "44100",
            str(wav),
        ],
        check=True,
    )
    assert audio.probe_duration(wav) == pytest.approx(2.0, abs=0.01)


def test_cli_reports_non_numeric_duration(demo_dir, monkeypatch, capsys):
    (demo_dir / "minus.mp3").write_bytes(b"x")
    monkeypatch.setattr(audio, "capture_tool", lambda argv: b"N/A\n")
    assert main(["compile", str(demo_dir)]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert "N/A" in err
