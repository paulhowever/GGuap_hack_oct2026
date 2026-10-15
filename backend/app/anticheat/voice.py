from dataclasses import dataclass

import numpy as np

from app.f0.base import F0Track
from app.scoring.grid import PITCHED
from app.scoring.synth import iter_notes

LONG_NOTE_S = 0.4
EDGE_S = 0.1
MIN_FRAMES = 10
MIN_NOTES = 2
FLAT_MAX_CENTS = 4.0
HARM_MIN = 0.01
HARM_FRAMES = 8
HARM_WIN_S = 0.064
HARM_MAX_K = 8


@dataclass(frozen=True)
class VoiceStats:
    notes: int
    jitter_c: float | None
    harm: float | None

    @property
    def not_voice(self) -> bool:
        if self.notes < MIN_NOTES or self.jitter_c is None:
            return False
        return self.jitter_c < FLAT_MAX_CENTS or (self.harm is not None and self.harm < HARM_MIN)


def detrended_jitter(t: np.ndarray, hz: np.ndarray) -> float:
    cents = 1200.0 * np.log2(hz / np.median(hz))
    x = t - t.mean()
    return float(np.std(cents - np.polyval(np.polyfit(x, cents, 1), x)))


def harmonic_ratio(audio: np.ndarray, sr: int, times: np.ndarray, hz: np.ndarray) -> float | None:
    win = int(HARM_WIN_S * sr)
    nfft = 1 << (8 * win - 1).bit_length()
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    window = np.hanning(win)
    ratios = []
    for t, f0 in zip(times, hz, strict=True):
        start = round(t * sr) - win // 2
        if start < 0 or start + win > audio.size:
            continue
        power = np.abs(np.fft.rfft(audio[start : start + win] * window, nfft)) ** 2
        peaks = [
            float(power[(freqs > 0.97 * k * f0) & (freqs < 1.03 * k * f0)].max())
            for k in range(1, HARM_MAX_K + 1)
            if k * f0 < 0.45 * sr
        ]
        ratios.append(sum(peaks[1:]) / max(peaks[0], 1e-12))
    return float(np.median(ratios)) if ratios else None


def voice_stats(
    audio: np.ndarray, sr: int, track: F0Track, ref: dict, wav_t0: float, lag_s: float, conf_min: float
) -> VoiceStats:
    song_t = wav_t0 + track.t - lag_s
    voiced = (track.conf >= conf_min) & (track.hz > 0)
    jitters: list[float] = []
    harms: list[float] = []
    for _, note in iter_notes(ref):
        if note["type"] not in PITCHED or note["d"] <= LONG_NOTE_S:
            continue
        inside = (song_t >= note["t"] + EDGE_S) & (song_t <= note["t"] + note["d"] - EDGE_S)
        sel = np.flatnonzero(voiced & inside)
        if sel.size < MIN_FRAMES:
            continue
        jitters.append(detrended_jitter(track.t[sel], track.hz[sel]))
        pick = sel[np.linspace(0, sel.size - 1, HARM_FRAMES).astype(int)]
        harm = harmonic_ratio(audio, sr, track.t[pick], track.hz[pick])
        if harm is not None:
            harms.append(harm)
    return VoiceStats(
        notes=len(jitters),
        jitter_c=round(float(np.median(jitters)), 2) if jitters else None,
        harm=round(float(np.median(harms)), 4) if harms else None,
    )
