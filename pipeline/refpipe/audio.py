import subprocess
from pathlib import Path

import numpy as np

from refpipe.errors import RefpipeError


def run_tool(argv: list[str]) -> None:
    try:
        subprocess.run(argv, check=True)
    except FileNotFoundError as exc:
        raise RefpipeError(f"{argv[0]} not found in PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RefpipeError(f"{argv[0]} exited with code {exc.returncode}") from exc


def capture_tool(argv: list[str]) -> bytes:
    try:
        return subprocess.run(argv, check=True, capture_output=True).stdout
    except FileNotFoundError as exc:
        raise RefpipeError(f"{argv[0]} not found in PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip()
        raise RefpipeError(f"{argv[0]} exited with code {exc.returncode}: {detail}") from exc


def ffprobe_argv(path: Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]


def probe_duration(path: Path) -> float:
    out = capture_tool(ffprobe_argv(path)).decode(errors="replace").strip()
    try:
        return round(float(out), 3)
    except ValueError as exc:
        raise RefpipeError(f"{path}: ffprobe reported no duration ({out!r})") from exc


def ffmpeg_cut_argv(
    src: Path, dst: Path, t0: float, t1: float, fade_in: float = 0.3, fade_out: float = 1.0
) -> list[str]:
    duration = t1 - t0
    fades = f"afade=t=in:d={fade_in:g},afade=t=out:st={duration - fade_out:.3f}:d={fade_out:g}"
    return [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        f"{t0:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(src),
        "-af",
        fades,
        "-ar",
        "44100",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(dst),
    ]


def decode_argv(path: Path, sr: int) -> list[str]:
    return ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]


def load_audio(path: Path, sr: int) -> np.ndarray:
    return np.frombuffer(capture_tool(decode_argv(path, sr)), dtype=np.float32).copy()
