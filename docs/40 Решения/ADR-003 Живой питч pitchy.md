---
tags: [adr]
status: draft
updated: 2026-10-08
---

# ADR-003 Живой питч pitchy

**Статус:** принято · **Дата:** 2026-10-08 · **Решили:** команда

## Контекст
aubio (как в AllKaraoke) под GPL-3 и требует WASM в Worker — лицензионный и интеграционный риск.

## Решение
Живой питч — pitchy (MIT, McLeod) в AudioWorklet.

## Альтернативы
aubiojs yinfft; свой YIN; ONNX-модели (SwiftF0/fnaught) через onnxruntime-web.

## Последствия
Нет WASM, лицензия репо остаётся MIT. Точность добирает финальная оценка на бэкенде.

## Связанные
- [[Решения (ADR)]]
