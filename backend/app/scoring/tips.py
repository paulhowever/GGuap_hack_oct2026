import numpy as np

from app.scoring.latency import Latency
from app.scoring.metrics import LineMetrics, NoteMetrics

PRIORITY = {
    "silence": 1,
    "golden_miss": 2,
    "flat": 3,
    "sharp": 3,
    "late": 4,
    "early": 4,
    "unstable": 5,
    "octave_info": 6,
    "praise": 7,
}
SEVERITY = {"octave_info": "info", "praise": "good"}
SILENCE_COVERAGE = 0.2
GOLDEN_MISS_HIT = 0.5
FLAT_SHARE = 0.6
FLAT_TOL_FRAC = 0.6
TIMING_MS = 120
UNSTABLE_D_S = 0.4
UNSTABLE_C = 60
PRAISE_AT = 90


def short(text: str, n: int = 22) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def r10(x: float) -> int:
    return int(round(abs(x) / 10.0) * 10)


def line_tip(
    line: LineMetrics, notes: list[NoteMetrics], tol: float, praise_at: float = PRAISE_AT
) -> tuple[str, str] | None:
    s = short(line.text)
    if line.coverage < SILENCE_COVERAGE:
        return "silence", f"«{s}» почти не слышно — пой громче или ближе к микрофону"
    golden = [n for n in notes if n.type == "golden" and n.hit < GOLDEN_MISS_HIT]
    if golden:
        syl = golden[0].syl.replace("~", "").strip()
        if syl:
            return "golden_miss", f"золотая нота «{syl}» в «{s}» мимо — за неё двойные очки"
        return "golden_miss", f"золотая нота в «{s}» мимо — за неё двойные очки"
    cents = [n.cents for n in notes if n.cents is not None]
    if cents:
        med = float(np.median(cents))
        same = sum(1 for c in cents if np.sign(c) == np.sign(med)) / len(cents)
        if abs(med) > FLAT_TOL_FRAC * tol and same >= FLAT_SHARE:
            word, code = ("ниже", "flat") if med < 0 else ("выше", "sharp")
            return code, f"«{s}» {word} на ~{r10(med)} центов"
    onsets = [n.onset_ms for n in notes if n.onset_ms is not None]
    if onsets:
        mean = float(np.mean(onsets))
        if mean > TIMING_MS:
            return "late", f"«{s}» опаздываешь на ~{r10(mean)} мс"
        if mean < -TIMING_MS:
            return "early", f"«{s}» спешишь на ~{r10(mean)} мс"
    if any(n.d > UNSTABLE_D_S and n.stab_c is not None and n.stab_c > UNSTABLE_C for n in notes):
        return "unstable", f"«{s}» длинные ноты гуляют — держи ровнее"
    if line.score >= praise_at:
        return "praise", f"«{s}» — отлично!"
    return None


def build_tips(
    notes: list[NoteMetrics],
    lines: list[LineMetrics],
    latency: Latency,
    octave: int,
    tol: float,
    praise_at: float = PRAISE_AT,
) -> tuple[list[dict], dict[int, str]]:
    candidates: list[dict] = []
    per_line: dict[int, str] = {}
    for line in lines:
        found = line_tip(line, [n for n in notes if n.line == line.i], tol, praise_at)
        if found:
            code, text = found
            per_line[line.i] = text
            candidates.append({"code": code, "sev": SEVERITY.get(code, "warn"), "line": line.i, "text": text})
    if abs(latency.residual_ms) > TIMING_MS:
        code = "late" if latency.residual_ms > 0 else "early"
        word = "позже" if code == "late" else "раньше"
        ms = r10(latency.residual_ms)
        candidates.append(
            {
                "code": code,
                "sev": "warn",
                "line": None,
                "text": f"в целом поёшь {word} минуса на ~{ms} мс — попробуй калибровку",
            }
        )
    if octave:
        word = "ниже" if octave < 0 else "выше"
        candidates.append(
            {
                "code": "octave_info",
                "sev": "info",
                "line": None,
                "text": f"поёшь на октаву {word} — это нормально, не штрафуем",
            }
        )
    only_praise = all(c["code"] == "praise" for c in candidates)
    pool = [c for c in candidates if only_praise or c["code"] != "praise"]
    pool.sort(key=lambda c: (PRIORITY[c["code"]], -1 if c["line"] is None else c["line"]))
    picked: list[dict] = []
    seen: set[str] = set()
    for tip in pool:
        if tip["code"] in seen and tip["code"] != "silence":
            continue
        seen.add(tip["code"])
        picked.append(tip)
        if len(picked) == 3:
            break
    return picked, per_line
