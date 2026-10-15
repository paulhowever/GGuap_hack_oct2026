extends Node
## REST-клиент бэкенда (/api/v1) на HTTPRequest.
## Базовый адрес: window.VOICE_CONFIG.api, иначе origin страницы (игру отдаёт тот же
## FastAPI). Вне веба — http://localhost:8000.
## Все методы — корутины: `var r := await Api.get_songs()` → {ok, status, data, error}.
## Если бэкенда нет, а мы в моке/заглушке, список песен берётся из res://mock/.

const DESKTOP_BASE := "http://localhost:8000"
const PREFIX := "/api/v1"
const TIMEOUT_SEC := 10.0
const MOCK_TIMEOUT_SEC := 2.0
const MOCK_SONG := "res://mock/demo.reference.json"

var base_url: String = DESKTOP_BASE
var player_registered: bool = false


func _ready() -> void:
	base_url = _resolve_base()


func _resolve_base() -> String:
	if not OS.has_feature("web"):
		return DESKTOP_BASE
	var v = JavaScriptBridge.eval(
		"(function(){var c=window.VOICE_CONFIG||{};var a=c.api||'';"
		+ "if(/^https?:\\/\\//.test(a))return a;return location.origin+a;})()", true)
	var s := "" if v == null else str(v)
	return s.trim_suffix("/") if not s.is_empty() else DESKTOP_BASE


## GET /songs → Array элементов {id, title, artist, duration, difficulty, range_midi, license, top}.
func get_songs() -> Dictionary:
	# в моке бэкенда может не быть — не заставляем ждать полный таймаут
	var timeout := MOCK_TIMEOUT_SEC if VoiceBridge.is_mock() else TIMEOUT_SEC
	var r := await _request(HTTPClient.METHOD_GET, "/songs", null, timeout)
	if r.ok and r.data is Array:
		return r
	if VoiceBridge.is_mock():
		var demo := _mock_song_item()
		if not demo.is_empty():
			return {"ok": true, "status": 200, "data": [demo], "error": "", "mock": true}
	if r.ok:
		r.ok = false
		r.error = "bad_payload"
	return r


func get_song(id: String) -> Dictionary:
	return await _request(HTTPClient.METHOD_GET, "/songs/%s" % id.uri_encode())


## POST /players — регистрирует/обновляет ник для client_id.
func register_player(nickname: String) -> Dictionary:
	var cid := VoiceBridge.client_id()
	if cid.is_empty() or cid == VoiceBridge.STUB_CLIENT_ID:
		return {"ok": false, "status": 0, "data": null, "error": "no_client_id"}
	var r := await _request(HTTPClient.METHOD_POST, "/players",
		{"client_id": cid, "nickname": nickname.strip_edges().left(24), "avatar": {}})
	player_registered = r.ok
	return r


func _mock_song_item() -> Dictionary:
	if not FileAccess.file_exists(MOCK_SONG):
		return {}
	var ref = JSON.parse_string(FileAccess.get_file_as_string(MOCK_SONG))
	if not ref is Dictionary:
		return {}
	return {
		"id": ref.id, "title": ref.title, "artist": ref.artist,
		"duration": ref.audio.duration, "difficulty": ref.stats.difficulty,
		"range_midi": ref.stats.range_midi,
		"license": {"short": ref.license.get("recording", ""), "attribution": ref.license.get("attribution", "")},
		"top": null,
	}


func _request(method: int, path: String, body: Variant = null, timeout: float = TIMEOUT_SEC) -> Dictionary:
	var http := HTTPRequest.new()
	http.timeout = timeout
	add_child(http)
	var headers := PackedStringArray(["Accept: application/json"])
	var payload := ""
	if body != null:
		headers.append("Content-Type: application/json")
		payload = JSON.stringify(body)
	var err := http.request(base_url + PREFIX + path, headers, method, payload)
	if err != OK:
		http.queue_free()
		return {"ok": false, "status": 0, "data": null, "error": "net"}
	var res: Array = await http.request_completed
	http.queue_free()
	var result: int = res[0]
	var status: int = res[1]
	var bytes: PackedByteArray = res[3]
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "status": status, "data": null, "error": "net"}
	var data = JSON.parse_string(bytes.get_string_from_utf8()) if bytes.size() > 0 else null
	var ok := status >= 200 and status < 300
	var error := ""
	if not ok:
		error = str(data.get("detail", "http_%d" % status)) if data is Dictionary else "http_%d" % status
	return {"ok": ok, "status": status, "data": data, "error": error}
