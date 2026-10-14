import json
from pathlib import Path

import numpy as np
import soundfile as sf

from app.core.config import ROOT
from app.scoring.synth import synth_take


def click_track(duration: float, sr: int, period: float = 0.5) -> np.ndarray:
    out = np.zeros(int(round(duration * sr)), dtype=np.float32)
    n = int(0.02 * sr)
    click = (0.25 * np.sin(2 * np.pi * 1000.0 * np.arange(n) / sr) * np.linspace(1, 0, n)).astype(np.float32)
    for k in range(int(duration / period)):
        start = int(k * period * sr)
        end = min(start + n, out.size)
        out[start:end] += click[: end - start]
    return out


def build_demo(out_dir: Path, ref_path: Path, sr: int = 22050) -> dict:
    ref = json.loads(ref_path.read_text(encoding="utf-8"))
    ref["audio"]["minus"] = "/media/demo/minus.wav"
    ref["audio"]["guide"] = "/media/demo/guide.wav"
    duration = float(ref["audio"]["duration"])
    guide = synth_take(ref, sr=sr)
    minus = click_track(duration, sr) + 0.35 * synth_take(ref, sr=sr, octave=-1)
    out_dir.mkdir(parents=True, exist_ok=True)
    sf.write(out_dir / "guide.wav", guide, sr, subtype="PCM_16")
    sf.write(out_dir / "minus.wav", np.clip(minus, -1, 1), sr, subtype="PCM_16")
    (out_dir / "reference.json").write_text(
        json.dumps(ref, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    return ref


if __name__ == "__main__":
    build_demo(ROOT / "songs" / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
