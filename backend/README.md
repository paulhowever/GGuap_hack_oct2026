# backend

FastAPI (Паша). Маршруты: `/healthz`, `/api/v1/{version,health,songs,sessions,takes,players,leaderboard,challenges,published}`, `/c/{id}`, `/media` (файлы `songs/`).

Каверы (ADR-023): `POST /api/v1/published` публикует свой `ok`-дубль, `POST /api/v1/published/{take_id}/remove` снимает публикацию, `GET /api/v1/published?song_id=` — список, `GET /api/v1/published/{take_id}` — элемент, `/audio` — WAV с Range. Публикации хранятся в таблице `published_takes`, WAV — прежний `takes/<id>.wav`; `client_id` в ответах нет.

Статика на `/`: по умолчанию `web/`; собранную игру `dist/web` отдаёт `make dev` и `make demo` через `KARAOKE_WEB_DIR`.

Оценка score-v1, баланс — `contracts/scoring.json`. f0: только SwiftF0 (CPU, `KARAOKE_F0_ENGINE=swiftf0`); другие движки — после хакатона, сейчас любое другое значение роняет старт.

Переменные окружения:
- `KARAOKE_WEB_DIR` — каталог статики. `make backend` всегда задаёт его из переменной `WEB_DIR` и перекрывает значение из `.env`; другой каталог: `make backend WEB_DIR=...`.
- `KARAOKE_SECRET` — ключ подписи сессий; если не задан, создаётся один раз и хранится в `data/secret.key` (права 0600), поэтому перезапуск не ломает начатые дубли.
- `KARAOKE_DATA_DIR` — SQLite `app.db`, `takes/<id>.wav`, `secret.key`.
- `KARAOKE_SONGS_DIR` — каталог песен; битая папка не роняет `/api/v1/songs`, а пропускается и называется в `/api/v1/health` (`degraded`).
- `KARAOKE_PUBLIC_URL` — внешний адрес (туннель) для ссылки и QR дуэли; без него ссылка строится из Host запроса.

`.env` читается из текущего каталога (под `make` это `backend/`).
