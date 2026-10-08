---
tags: [research, godot]
status: draft
updated: 2026-10-08
---

# Godot MCP серверы

| Сервер | Тип | Заметки |
|---|---|---|
| Coding-Solo/godot-mcp | файловый + CLI | запуск проекта, debug-вывод, создание сцен/нод; выбран |
| bradypp/godot-mcp | файловый | альтернатива |
| GDAI MCP | через плагин в редакторе | живое дерево сцены, ставится в `addons/` |
| GodotLens (`godotlens-mcp`) | STDIO | не проверен |

Ограничение всех: ошибки web-сборки в браузере не видят — ловим через консоль браузера. Обзор: summerengine.com/blog/best-godot-mcp-server (пишет вендор одного из серверов).

## Связанные
- [[Godot и MCP]]
- [[ADR-010 Godot MCP]]
