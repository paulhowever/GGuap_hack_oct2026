# web

Аудио-движок игры. Godot только рисует и опрашивает мост `window.voice`; минус, микрофон, живой питч и запись дубля живут здесь на одном AudioContext.

| Файл | Что |
|---|---|
| `voice.js` | Настоящий мост `window.voice`; при `?mock=<mode>` ставит мок |
| `voice.mock.js` | Мок с тем же API: кадры по reference, результат из `mock/result.<mode>.json` |
| `tap.js` | AudioWorklet: pitchy (окно 2048, хоп 512) и PCM для записи дубля |
| `config.js` | `window.VOICE_CONFIG`: `api`, `lag_ms`, `difficulty`, `music_volume`, `aec`, `clarity_min`, `tol_cents`, `tap_url` |
| `dev.html` | Тестовая страница без Godot |
| `lib/` | Чистая логика: WAV, даунсэмплинг, тайминг, калибровка, мок-кадры, хоппер питча |
| `vendor/pitchy.bundle.js` | ESM-бандл pitchy + fft.js, собирается `npm run vendor` и коммитится |

## Команды

| Команда | Что делает |
|---|---|
| `npm install` | ставит pitchy и esbuild в `node_modules` |
| `npm run vendor` | пересобирает `vendor/pitchy.bundle.js` |
| `npm test` | пересобирает бандл и запускает `node --test` (без браузера) |
| `make test-web` | то же из корня репозитория |

## Проверка без Godot

1. `make backend`: FastAPI отдаёт `web/` на `/`.
2. http://localhost:8000/dev.html, нажать «Нажми, чтобы начать», разрешить микрофон.
3. Без микрофона: http://localhost:8000/dev.html?mock=perfect (ещё `offkey`, `octave`, `late200`, `silent`).

## Задержка

`lag_ms` берётся по приоритету: `configure`/`calibrate` в текущей сессии, затем `lag_ms` в `config.js` (на демо зашивается после калибровки на целевой цепочке), затем `localStorage['voice.lag_ms']`, затем оценка `outputLatency + baseLatency + latency трека` (0,02 с, если браузер её не отдаёт). Калибровка не удалась, если в `on_calibrated` `hits < 5`: `lag_ms` тогда прежний.

## План Б

«Скачать дубль» в dev.html сохраняет `take.wav` и `take.meta.json`. Положить их в `web/mock/`, открыть игру с `?mock=perfect` и нажать Alt+Shift+R: дубль уйдёт в настоящий `POST /api/v1/takes`.
