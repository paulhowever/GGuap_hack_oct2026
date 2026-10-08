---
tags: [research, pipeline]
status: draft
updated: 2026-10-08
---

# UltraSinger

- Репо: https://github.com/rakuri255/UltraSinger (MIT). Локальный клон: `refs/UltraSinger`.
- Пайплайн: Demucs (htdemucs) → Whisper (тайминги слов) → SwiftF0 (питч 60–400 Гц) → квантование к тональности → UltraStar TXT / MIDI.
- Предсказывает очки: simple (октава не важна) и accurate.
- Python 3.12, ffmpeg; GPU — только NVIDIA CUDA, large-модели Whisper просят >8 ГБ VRAM.
- Русский: свою align-модель через `--whisper_align_model` (например `jonatasgrosman/wav2vec2-large-xlsr-53-russian`).
- Авторы просят использовать только на CC-песнях и указывать UltraSinger в txt.

## Связанные
- [[Эталоны и пайплайн]]
