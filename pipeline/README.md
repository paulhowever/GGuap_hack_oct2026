# pipeline

`refpipe` (Паша): `from-midi`, `compile` (UltraStar TXT → reference.json), `cut`, `check`, `preview`, `credits`. Команда `import` (UltraSinger на CUDA-сервере) отложена и не реализована.

Зависимость на бэкенд подключена по пути (`../backend`): после любого изменения зависимостей бэкенда нужно выполнить `cd pipeline && uv lock`, иначе CI с `uv sync --locked` упадёт.

`from-midi` пишет только обычные ноты (`:`), поэтому `check` не пройдёт `golden_share` (5–15% золотых), пока золотые ноты (`*`) не добавлены в `song.txt` вручную.
