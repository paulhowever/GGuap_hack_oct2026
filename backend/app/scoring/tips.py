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


def short(text: str, n: int = 22) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def r10(x: float) -> int:
    return int(round(abs(x) / 10.0) * 10)


def line_tip(line: LineMetrics, notes: list[NoteMetrics], tol: float) -> tuple[str, str] | None:
    s = short(line.text)
    if line.coverage < 0.2:
        return "silence", f"«{s}» почти не слышно — пой громче или ближе к микрофону"
    golden = [n for n in notes if n.type == "golden" and n.hit < 0.5]
    if golden:
        return "golden_miss", f"золотая нота «{golden[0].syl.strip()}» в «{s}» мимо — за неё двойные очки"
    cents = [n.cents for n in notes if n.cents is not None]
    if cents:
        med = float(np.median(cents))
        same = sum(1 for c in cents if np.sign(c) == np.sign(med)) / len(cents)
        if abs(med) > 0.6 * tol and same >= 0.6:
            word, code = ("ниже", "flat") if med < 0 else ("выше", "sharp")
            return code, f"«{s}» {word} на ~{r10(med)} центов"
    onsets = [n.onset_ms for n in notes if n.onset_ms is not None]
    if onsets:
        mean = float(np.mean(onsets))
        if mean > 120:
            return "late", f"«{s}» опаздываешь на ~{r10(mean)} мс"
        if mean < -120:
            return "early", f"«{s}» спешишь на ~{r10(mean)} мс"
    if any(n.d > 0.4 and n.stab_c is not None and n.stab_c > 60 for n in notes):
        return "unstable", f"«{s}» длинные ноты гуляют — держи ровнее"
    if line.score >= 90:
        return "praise", f"«{s}» — отлично!"
    return None


def build_tips(
    notes: list[NoteMetrics], lines: list[LineMetrics], latency: Latency, octave: int, tol: float
) -> tuple[list[dict], dict[int, str]]:
    candidates: list[dict] = []
    per_line: dict[int, str] = {}
    for line in lines:
        found = line_tip(line, [n for n in notes if n.line == line.i], tol)
        if found:
            code, text = found
            per_line[line.i] = text
            candidates.append({"code": code, "sev": SEVERITY.get(code, "warn"), "line": line.i, "text": text})
    if abs(latency.residual_ms) > 120:
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
