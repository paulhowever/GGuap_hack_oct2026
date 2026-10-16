import json

import numpy as np
import pytest
import soundfile as sf

from refpipe import usdx
from refpipe.cli import main
from refpipe.preview import mix, render_melody, render_preview

SR = 8000


def test_melody_pitch_level_and_silence(demo_fixture):
    mel = render_melody(demo_fixture, SR, 12 * SR)
    segment = mel[int(2.6 * SR) : int(3.2 * SR)]
    spectrum = np.abs(np.fft.rfft(segment))
    freqs = np.fft.rfftfreq(len(segment), 1 / SR)
    assert freqs[spectrum.argmax()] == pytest.approx(261.63, abs=2.0)
    assert np.abs(mel).max() == pytest.approx(10 ** (-12 / 20), abs=0.005)
    assert not mel[: int(2.49 * SR)].any()


def test_shift_moves_melody(demo_fixture):
    mel = render_melody(demo_fixture, SR, 12 * SR, shift_ms=100)
    assert not mel[int(2.5 * SR) : int(2.59 * SR)].any()
    assert np.abs(mel[int(2.65 * SR) : int(2.7 * SR)]).max() > 0.1


def test_mix_pads_and_clips():
    out = mix(np.full(4, 0.9, dtype=np.float32), np.full(6, 0.3, dtype=np.float32))
    assert out.tolist() == pytest.approx([1.0, 1.0, 1.0, 1.0, 0.3, 0.3])


def test_preview_without_minus_uses_duration(demo_fixture):
    assert len(render_preview(demo_fixture, np.zeros(0, dtype=np.float32), SR)) == 12 * SR


def test_cli_preview(demo_dir, tmp_path):
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 0
    out = tmp_path / "demo.wav"
    assert main(["preview", str(demo_dir), "--out", str(out)]) == 0
    info = sf.info(out)
    assert info.samplerate == 44100
    assert info.duration == pytest.approx(12.0, abs=0.01)


def test_cli_apply_gap_shift(demo_dir, tmp_path):
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 0
    assert (
        main(["preview", str(demo_dir), "--shift-ms", "20", "--apply", "--out", str(tmp_path / "p.wav")]) == 0
    )
    assert usdx.read(demo_dir / "song.txt").gap_ms == 2520.0
    ref = json.loads((demo_dir / "reference.json").read_text(encoding="utf-8"))
    assert ref["timing"]["gap_ms"] == 2520
    assert ref["audio"]["duration"] == 12.0
    assert ref["lines"][0]["t0"] == 2.52


def test_cli_apply_rejected_shift_leaves_files_untouched(demo_dir, tmp_path):
    assert main(["compile", str(demo_dir), "--duration", "12"]) == 0
    song_before = (demo_dir / "song.txt").read_bytes()
    ref_before = (demo_dir / "reference.json").read_bytes()
    out = tmp_path / "p.wav"
    assert main(["preview", str(demo_dir), "--shift-ms", "4000", "--apply", "--out", str(out)]) == 2
    assert (demo_dir / "song.txt").read_bytes() == song_before
    assert (demo_dir / "reference.json").read_bytes() == ref_before
    assert not out.exists()


def test_cli_preview_needs_reference(tmp_path, capsys):
    assert main(["preview", str(tmp_path)]) == 2
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
@pytest.mark.parametrize("flags", [[], ["--apply"]], ids=["render", "apply"])
def test_cli_preview_rejects_malformed_reference(tmp_path, capsys, content, message, flags):
    (tmp_path / "reference.json").write_bytes(content)
    assert main(["preview", str(tmp_path), "--out", str(tmp_path / "p.wav"), *flags]) == 2
    err = capsys.readouterr().err
    assert err.startswith("refpipe: ")
    assert message in err
    assert not (tmp_path / "p.wav").exists()
