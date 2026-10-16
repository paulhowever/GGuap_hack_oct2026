# Караоке-баттл

Браузерная игра для хакатона «Звук» × ИТМО (17–18 октября 2026, кейс 4): поёшь фрагмент песни, получаешь оценку попадания в мелодию и ритм с объяснением по строкам, улучшаешь результат и вызываешь друзей на дуэль.

Godot рисует, JS слушает, бэкенд судит.

## Структура

| Папка | Что | Владелец |
|---|---|---|
| `godot/` | Godot 4 проект, web export | Макс |
| `web/` | `voice.js`: минус, микрофон, живой питч (pitchy), запись дубля; мок | Паша |
| `backend/` | FastAPI: оценка дублей, лидерборд, дуэли | Паша |
| `pipeline/` | `refpipe`: UltraStar TXT ↔ reference.json; импорт треков — после хакатона (ADR-022) | Паша |
| `contracts/` | `scoring.json`, фикстуры | Паша + Макс |
| `songs/` | эталоны, минусы, лицензии — [как сделать песню](songs/README.md) | Сеня |
| `docs/` | Obsidian-волт: архитектура, контракты, решения, план | все |

## Запустить игру (без Godot)

Собранная игра лежит в репозитории, в `dist/web`. Нужны только [uv](https://docs.astral.sh/uv/) и Chrome или Edge.

```bash
git clone <url>
cd GGuap_hack_oct2026/backend
uv sync                                   # только в первый раз
uv run uvicorn app.main:app --port 8000   # окно не закрывать
```

Открыть http://localhost:8000/ (микрофон, лучше в наушниках) или http://localhost:8000/?mock=perfect (без микрофона).
Открывать `dist/web/index.html` двойным щелчком нельзя: игре нужен бэкенд, а микрофону — `localhost`.

Обновить сборку (нужен Godot 4.8-dev7 с шаблонами Web): `powershell -ExecutionPolicy Bypass -File scripts\build-web.ps1`, затем закоммитить `dist/web`.

## Быстрый старт

Движок без Godot:

```bash
make setup
make backend
```

Открыть http://localhost:8000/dev.html. Мок без микрофона: http://localhost:8000/dev.html?mock=perfect

Игра: положить экспорт Godot в `dist/web` (`make export-web GODOT_PROJECT=<путь к проекту>` или скопировать готовый), затем

```bash
make demo
```

Открыть http://localhost:8000/. Мок без микрофона: http://localhost:8000/?mock=perfect

Windows без `make`: [docs/65 QA/Запуск сборки под Windows.md](docs/65%20QA/Запуск%20сборки%20под%20Windows.md)

Документация: [docs/00 Главная.md](docs/00%20Главная.md)
