---
tags: [архитектура, godot, макс]
status: draft
updated: 2026-10-08
---

# Godot и MCP

**Версия и экспорт.**
- Godot 4.7.2.stable, у всех та же версия и те же шаблоны. Только GDScript, C# на web не поддерживается. Рендерер Compatibility, частицы CPUParticles2D.
- В пресете Web (коммитим):
  - `variant/thread_support=false`;
  - `extensions_support=false`;
  - `html/custom_html_shell=res://shell.html` с плейсхолдерами `$GODOT_URL $GODOT_CONFIG $GODOT_HEAD_INCLUDE $GODOT_THREADS_ENABLED $GODOT_PROJECT_NAME` и оверлеем unlock;
  - `head_include`: `<script src="config.js"></script><script type="module" src="voice.js"></script>`;
  - `canvas_resize_policy=2`, без PWA.
- «Run in Browser» не используем, в браузере проверяем только `dist/` через FastAPI.

```gdscript
extends Node
signal unlocked(d: Dictionary)
signal song_ready(ref: Dictionary)
signal song_ended
signal result_received(r: Dictionary)
signal calibrated(d: Dictionary)
signal bridge_error(code: String)
var _js: JavaScriptObject
var _cb: JavaScriptObject
var _mock: Node
func _ready() -> void:
	if OS.has_feature("web"):
		_js = JavaScriptBridge.get_interface("voice")
	if _js == null:
		_mock = preload("res://autoload/mock_voice.gd").new()
		add_child(_mock)
		_mock.event.connect(_dispatch)
		return
	_cb = JavaScriptBridge.create_callback(_on_js)
	_js.subscribe(_cb)
func configure(o: Dictionary) -> void:
	if _mock: _mock.configure(o) else: _js.configure(JSON.stringify(o))
func load_song(id: String) -> void:
	if _mock: _mock.load_song(id) else: _js.load_song(id)
func start() -> void:
	if _mock: _mock.start() else: _js.start()
func stop() -> void:
	if _mock: _mock.stop() else: _js.stop()
func submit(player: String, challenge_id := "") -> void:
	if _mock: _mock.submit(player, challenge_id) else: _js.submit(player, challenge_id)
func calibrate() -> void:
	if _mock: _mock.calibrate() else: _js.calibrate()
func poll() -> Dictionary:
	var s: String = _mock.poll() if _mock else str(_js.poll())
	var p = JSON.parse_string(s)
	return p if p is Dictionary else {"t_now": 0.0, "state": "idle", "frames": []}
func url_param(k: String) -> String:
	return str(JavaScriptBridge.eval("new URLSearchParams(location.search).get('%s')||''" % k)) if _js else ""
func _on_js(args: Array) -> void:
	_dispatch(str(args[0]), str(args[1]) if args.size() > 1 else "{}")
func _dispatch(name: String, json: String) -> void:
	var p = JSON.parse_string(json)
	match name:
		"on_unlocked": unlocked.emit(p)
		"on_ready": song_ready.emit(p)
		"on_song_end": song_ended.emit()
		"on_result": result_received.emit(p)
		"on_calibrated": calibrated.emit(p)
		"on_error": bridge_error.emit(str(p.get("code", "")))
```
`mock_voice.gd` отдаёт poll из `res://mock/<id>.reference.json` и результат из `res://mock/result.json`. Фикстуры копируются из `contracts/fixtures` скриптом, руками не правятся.

**NoteLane (Control, `_draw`).**
- Страница = текущая строка, как в UltraStar. Скролл — stretch.
- `t = max(prev, t_now)`.
- `x = lane_x + (t − l.t0)/(l.t1 − l.t0)·w`, `y = bottom − (midi − lo)/(hi − lo)·h`, где `lo = min − 2`, `hi = max(min + 12, max + 2)`.
- Кадр голоса: `m = 69 + 12·log2(hz/440)`, затем `m += 12·round((n.midi − m)/12)`. Попадание: `|m − midi|·100 ≤ tol_cents` из `on_ready.scoring`.
- Живой счёт с пометкой «≈» считается косметически и взвешивается по длине нот (golden ×2).

**Сцены.**
- autoload: VoiceBridge, Api (HTTPRequest и мок), Session (ник, song_id, challenge_id, difficulty, last_result, попытка).
- Порядок работы: мок в редакторе → web-экспорт с `?mock=perfect` → настоящий voice.js.

**MCP.** Coding-Solo/godot-mcp:
- файловый и CLI, в репо ничего не ставится;
- GDAI отвергнут, потому что требует `addons/`.
```
git clone https://github.com/Coding-Solo/godot-mcp ~/tools/godot-mcp && cd ~/tools/godot-mcp && git checkout <sha> && npm ci && npm run build
claude mcp add godot -s local -e GODOT_PATH=/Applications/Godot.app/Contents/MacOS/Godot -- node ~/tools/godot-mcp/build/index.js
```
- Сборка из клона с зафиксированным коммитом, а не через npx latest.
- Проверка: `get_godot_version`, затем `run_project` на сцене Sing в мок-режиме и `get_debug_output`.

## Связанные
- [[Контракты]]
- [[ADR-001 Godot web и JS-мост]]
- [[ADR-010 Godot MCP]]
- [[Godot MCP серверы]]
