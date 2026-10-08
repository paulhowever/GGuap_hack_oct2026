# backend

FastAPI (Паша): `/healthz`, `/api/v1/{version,health,songs,takes,leaderboard,challenges}`, `/c/{id}`, раздача `dist/web` и `/media`.
Оценка score-v1, f0: SwiftF0 (CPU) или torchcrepe (CUDA, `F0_ENGINE`). Баланс — `contracts/scoring.json`.
