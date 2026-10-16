# deploy

VPS: `docker compose up -d` (api + caddy, автоHTTPS) — не сделано: `compose.yml` и `Caddyfile` появятся после хакатона. Демо идёт локально (`make demo`).

`KARAOKE_SECRET` в `.env` — ключ подписи токенов сессии (`openssl rand -hex 32`). Без него ключ создаётся один раз в `data/secret.key` и переживает рестарты.
