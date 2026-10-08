---
tags: [research, референс]
status: draft
updated: 2026-10-08
---

# AllKaraoke

- Репо: https://github.com/Asvarox/allkaraoke (MIT), сайт allkaraoke.party. Локальный клон: `refs/allkaraoke`.
- TypeScript/React/Vite, Cloudflare Workers, PeerJS для телефона-микрофона.
- Питч: aubiojs (стратегии `src/modules/game-engine/input/mic-strategies/aubio.ts`, `yin.ts`).
- Оценка: `distance` в полутонах без учёта октавы, `tolerance`, `playerNote`, бонус за вибрато, golden/rap/freestyle. См. `context.md`, `docs/player-note-calculation-logic.md`, `src/modules/game-engine/game-state/player-state.ts`.
- Input lag настраивается на игрока (`docs/input-management.md`).
- Глобальный лидерборд за 14 дней, порог 1 000 000 очков, msgpack-блоб нот для будущей верификации (`docs/leaderboard.md`).

## Связанные
- [[Оценка и объяснение]]
- [[ADR-009 AllKaraoke как референс]]
