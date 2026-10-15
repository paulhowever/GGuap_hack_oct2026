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
4. Без бэкенда: `cd web && python3 -m http.server 8000`. Мок (`?mock=…`) и живой питч работают и на статическом сервере; бэкенд из ветки pasha/backend нужен только настоящему движку для `load_song` и `submit`.
5. Отладка: добавить `?debug=1` (можно вместе с `?mock=…`). В правом нижнем углу появится оверлей: версии api и web, режим, sr, задержки, текущий тон, кадры/с, client_id, статус токена сессии, последний вердикт ноты и integrity. Alt+Shift+D копирует его текст в буфер обмена для баг-репорта. Строка `web —` значит, что статика отдаётся из `web/` без `make assemble`.

## Для Godot (шелл и VoiceBridge)

- `unlock()` возвращает `Promise<boolean>`. Оверлей прячем только при `true`; при `false` показываем ошибку из `on_error` и даём нажать ещё раз: повторный `unlock()` пробует заново.
- `on_error`, пришедший до `subscribe`, повторно не доставляется: липкий только `on_unlocked`.
- Повтор `on_unlocked` приходит синхронно внутри `subscribe()`, поэтому VoiceBridge должен сохранить payload и переизлучить сигнал через `call_deferred`.
- Дорожку нот рисовать только в `state: "playing"` из `poll()`; `level` использовать для индикатора микрофона.

## Задержка

`lag_ms` берётся по приоритету: `configure`/`calibrate` в текущей сессии, затем `lag_ms` в `config.js` (на демо зашивается после калибровки на целевой цепочке), затем `localStorage['voice.lag_ms']`, затем оценка `outputLatency + baseLatency + latency трека` (0,02 с, если браузер её не отдаёт). Калибровка не удалась, если в `on_calibrated` `hits < 5`: `lag_ms` тогда прежний.

## План Б

«Скачать дубль» в dev.html сохраняет `take.wav` и `take.meta.json`. Положить их в `web/mock/`, открыть игру с `?mock=perfect` и нажать Alt+Shift+R: дубль уйдёт в настоящий `POST /api/v1/takes`.
