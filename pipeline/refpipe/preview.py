import argparse
from pathlib import Path

import numpy as np
import soundfile as sf

from refpipe import audio, paths, usdx
from refpipe.compile import PITCHED, compile_reference, read_reference, write_reference
from refpipe.meta import load_meta

SR = 44100
FADE_S = 0.01
GAIN_DB = -12.0


def render_melody(
    ref: dict, sr: int, length: int, shift_ms: float = 0.0, gain_db: float = GAIN_DB
) -> np.ndarray:
    out = np.zeros(length, dtype=np.float32)
    amp = 10 ** (gain_db / 20)
    for line in ref["lines"]:
        for note in line["notes"]:
            if note["type"] not in PITCHED:
                continue
            start = max(0, round((note["t"] + shift_ms / 1000) * sr))
            end = min(length, round((note["t"] + note["d"] + shift_ms / 1000) * sr))
            if end <= start:
                continue
            k = np.arange(end - start)
            freq = 440.0 * 2 ** ((note["midi"] - 69) / 12)
            tone = amp * np.sin(2 * np.pi * freq * k / sr)
            fade = min(round(FADE_S * sr), (end - start) // 2)
            if fade > 0:
                ramp = 0.5 - 0.5 * np.cos(np.pi * np.arange(fade) / fade)
                tone[:fade] *= ramp
                tone[-fade:] *= ramp[::-1]
            out[start:end] += tone.astype(np.float32)
    return out


def mix(minus: np.ndarray, melody: np.ndarray) -> np.ndarray:
    out = np.zeros(max(len(minus), len(melody)), dtype=np.float32)
    out[: len(minus)] += minus
    out[: len(melody)] += melody
    return np.clip(out, -1.0, 1.0)


def render_preview(ref: dict, minus: np.ndarray, sr: int = SR, shift_ms: float = 0.0) -> np.ndarray:
    length = max(len(minus), round(ref["audio"]["duration"] * sr))
    return mix(minus, render_melody(ref, sr, length, shift_ms))


def apply_gap_shift(song_dir: Path, shift_ms: float) -> dict:
    duration = read_reference(song_dir / "reference.json")["audio"]["duration"]
    song = usdx.read(song_dir / "song.txt")
    song.gap_ms = round(song.gap_ms + shift_ms, 3)
    ref = compile_reference(song, load_meta(song_dir / "meta.yaml"), song_dir.resolve().name, duration)
    usdx.write(song, song_dir / "song.txt")
    write_reference(ref, song_dir / "reference.json")
    return ref


def cmd(args: argparse.Namespace) -> int:
    if args.apply:
        ref, shift = apply_gap_shift(args.song_dir, args.shift_ms), 0.0
    else:
        ref, shift = read_reference(args.song_dir / "reference.json"), args.shift_ms
    minus_path = args.song_dir / "minus.mp3"
    minus = audio.load_audio(minus_path, SR) if minus_path.exists() else np.zeros(0, dtype=np.float32)
    out = args.out or paths.REPO_ROOT / "data" / "preview" / f"{ref['id']}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, render_preview(ref, minus, SR, shift), SR, subtype="PCM_16")
    print(f"{out}: GAP {ref['timing']['gap_ms']} ms, preview shift {shift:+g} ms")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("preview", help="render minus plus reference sine at -12 dB to WAV")
    p.add_argument("song_dir", type=Path)
    p.add_argument("--shift-ms", type=float, default=0.0)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--out", type=Path, default=None)
    p.set_defaults(func=cmd)
