extends Node
## Мост к аудио-движку на странице (window.voice из web/voice.js).
## Godot только рисует и опрашивает: минус, микрофон, живой питч и запись дубля — в JS.
##
## События JS приходят через voice.subscribe(cb) как (name, json). Повтор липкого
## on_unlocked приходит синхронно прямо внутри subscribe(), поэтому все события
## переизлучаем через call_deferred — подписчики Godot успеют подключиться.
##
## Вне веба (редактор/десктоп) или если window.voice нет — встроенная заглушка:
## ведёт себя как ?mock=perfect (кадры по res://mock/<id>.reference.json,
## результат из res://mock/result.perfect.json).

signal unlocked(info: Dictionary)          # {sr, noise_db, lag_ms, bt_suspect}
signal song_ready(ref: Dictionary)         # reference + {scoring: {tol_cents}, lag_ms}
signal note_judged(verdict: Dictionary)    # {i, line, type, hit, cents, onset_ms}
signal song_ended(t: float)
signal result_received(result: Dictionary) # контракт TakeResult
signal calibrated(lag_ms: int, hits: int)
signal bridge_error(code: String, msg: String)
## Каждый кадр после poll(): новые кадры питча лежат в `frames`.
signal polled

const MOCK_DIR := "res://mock/"
const STUB_HOP := 512.0 / 48000.0
const STUB_START_DELAY := 0.15
const STUB_SUBMIT_DELAY := 0.5
## Как в web/lib/calibration.js: первый щелчок через 0.6 с, 8 щелчков через 0.5 с.
const CAL_LEAD := 0.6
const CAL_GAP := 0.5
const CAL_CLICKS := 8
const CAL_MIN_HITS := 5
const STUB_CLIENT_ID := "00000000-0000-4000-8000-000000000000"

## Последний результат poll(): часы песни (единственные часы игры), состояние, уровень.
var t_now: float = 0.0
var state: String = "idle"            # idle | playing | ended
var level: float = 0.0
## Кадры питча, пришедшие за этот кадр: [{t, hz, conf, rms}, ...]
var frames: Array = []

var is_unlocked: bool = false
var unlock_info: Dictionary = {}
var is_calibrating: bool = false
var last_error: String = ""

var _js: JavaScriptObject
var _cb: JavaScriptObject              # держим ссылку, иначе GC уберёт колбэк
var _stub: Dictionary = {}


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	# опрашиваем раньше сцен, чтобы в их _process уже были свежие t_now/frames
	process_priority = -100
	if OS.has_feature("web"):
		_js = JavaScriptBridge.get_interface("voice")
		if _js == null:
			push_warning("VoiceBridge: window.voice не найден — работаю как заглушка")
	if _js:
		_cb = JavaScriptBridge.create_callback(_on_js_event)
		_js.subscribe(_cb)
	else:
		_stub = {"ref": {}, "state": "idle", "start_ms": 0, "last_t": 0.0, "next_note": 0, "notes": []}
		# заглушка «разблокирована» сразу — жест пользователя не нужен
		_emit_deferred.call_deferred("on_unlocked",
			JSON.stringify({"sr": 48000, "noise_db": -62, "lag_ms": Session.lag_ms, "bt_suspect": false}))
	Session.difficulty_changed.connect(func(_d: String) -> void: configure_from_session())
	Session.music_volume_changed.connect(func(_v: float) -> void: configure_from_session())
	Session.lag_changed.connect(func(_v: int) -> void:
		if Session.is_calibrated or Session.lag_manual:
			configure_from_session())


func is_web_bridge() -> bool:
	return _js != null


## Режим мока (?mock=perfect и т.п.) или встроенная заглушка.
func is_mock() -> bool:
	if _js == null:
		return true
	return str(_js._mode) != "real"


func url_param(key: String) -> String:
	if not OS.has_feature("web"):
		return ""
	var v = JavaScriptBridge.eval(
		"new URLSearchParams(location.search).get(%s) || ''" % JSON.stringify(key), true)
	return "" if v == null else str(v)


# --- Команды в JS -----------------------------------------------------------

## Повторная попытка разблокировки (обычно её делает оверлей shell.html).
func unlock() -> void:
	if _js:
		_js.unlock()


func configure(options: Dictionary) -> void:
	if _js:
		_js.configure(JSON.stringify(options))


## Отправить в JS сложность, громкость и (если известна) задержку из Session.
func configure_from_session() -> void:
	var o := {"difficulty": Session.difficulty, "music_volume": Session.music_volume}
	if Session.is_calibrated or Session.lag_manual:
		o["lag_ms"] = Session.lag_ms
	configure(o)


func load_song(id: String) -> void:
	if _js:
		_js.load_song(id)
	else:
		_stub_load_song(id)


func start() -> void:
	if _js:
		_js.start()
	else:
		_stub_start()


func stop() -> void:
	if _js:
		_js.stop()
	elif _stub.state == "playing":
		_stub.state = "ended"


func submit(player: String, challenge_id: String = "") -> void:
	if _js:
		_js.submit(player, challenge_id if not challenge_id.is_empty() else null)
	else:
		_stub_submit(player)


## Калибровка задержки. Результат — сигнал calibrated(lag_ms, hits).
func calibrate() -> void:
	if is_calibrating:
		return
	is_calibrating = true
	if _js:
		_js.calibrate()
	else:
		get_tree().create_timer(CAL_LEAD + CAL_GAP * (CAL_CLICKS - 1) + 0.6).timeout.connect(func() -> void:
			_dispatch("on_calibrated", JSON.stringify({"lag_ms": Session.lag_ms, "hits": CAL_CLICKS})))


func client_id() -> String:
	if _js == null:
		return STUB_CLIENT_ID
	var v = _js.client_id()
	return "" if v == null else str(v)


# --- Прослушивание последнего дубля (голос + минус) ---------------------------
# Дубль живёт только в памяти страницы: после перезагрузки его нет (available=false).

## Играть с позиции from_sec (< 0 — продолжить с текущей, после конца — с начала).
func review_play(from_sec: float = -1.0) -> void:
	if _js:
		_js.review_play(from_sec)
	else:
		_stub_review_play(from_sec)


func review_pause() -> void:
	if _js:
		_js.review_pause()
	elif _stub_review_is_playing():
		_stub.review.pos = _stub_review_pos()
		_stub.review.playing = false


func review_seek(t_sec: float) -> void:
	if _js:
		_js.review_seek(t_sec)
	elif _stub.has("review"):
		var r: Dictionary = _stub.review
		r.pos = clampf(t_sec, 0.0, float(r.dur))
		r.start_ms = Time.get_ticks_msec()
		r.start_pos = r.pos


func review_stop() -> void:
	if _js:
		_js.review_stop()
	elif _stub.has("review"):
		_stub.review.playing = false
		_stub.review.pos = 0.0


## {available, state: idle|playing|paused|ended, t, duration, song_id, take_id}
func review_state() -> Dictionary:
	var empty := {"available": false, "state": "idle", "t": 0.0, "duration": 0.0, "song_id": null, "take_id": null}
	if _js:
		var raw = _js.review_state()
		var p = JSON.parse_string(str(raw)) if raw != null else null
		return p if p is Dictionary else empty
	if not _stub.has("review"):
		return empty
	var r: Dictionary = _stub.review
	var t := _stub_review_pos()
	if bool(r.playing) and t >= float(r.dur):
		r.playing = false
		r.pos = float(r.dur)
	var st := "playing" if bool(r.playing) else ("ended" if t >= float(r.dur) else "paused")
	return {"available": true, "state": st, "t": t, "duration": float(r.dur),
		"song_id": r.song_id, "take_id": r.take_id}


# --- Опрос ------------------------------------------------------------------

func _process(_delta: float) -> void:
	var p = null
	if _js:
		var raw = _js.poll()
		p = JSON.parse_string(str(raw)) if raw != null else null
	else:
		p = _stub_poll()
	if p is Dictionary:
		t_now = float(p.get("t_now", 0.0))
		state = str(p.get("state", "idle"))
		level = float(p.get("level", 0.0))
		var f = p.get("frames", [])
		frames = f if f is Array else []
	else:
		frames = []
	polled.emit()


# --- События из JS ----------------------------------------------------------

func _on_js_event(args: Array) -> void:
	if args.is_empty():
		return
	var event_name := str(args[0])
	var json := str(args[1]) if args.size() > 1 and args[1] != null else "{}"
	# колбэк может прийти синхронно внутри вызова JS — не трогаем сцену прямо отсюда
	_emit_deferred.call_deferred(event_name, json)


func _emit_deferred(event_name: String, json: String) -> void:
	_dispatch(event_name, json)


func _dispatch(event_name: String, json: String) -> void:
	var parsed = JSON.parse_string(json)
	var p: Dictionary = parsed if parsed is Dictionary else {}
	match event_name:
		"on_unlocked":
			is_unlocked = true
			unlock_info = p
			last_error = ""
			# Пока игрок не калибровался и не крутил ±10, показываем оценку движка.
			if not Session.is_calibrated and not Session.lag_manual and p.has("lag_ms"):
				Session.lag_ms = int(p.lag_ms)
			configure_from_session()
			unlocked.emit(p)
		"on_ready":
			song_ready.emit(p)
		"on_note_judged":
			note_judged.emit(p)
		"on_song_end":
			song_ended.emit(float(p.get("t", 0.0)))
		"on_result":
			result_received.emit(p)
		"on_calibrated":
			is_calibrating = false
			calibrated.emit(int(p.get("lag_ms", Session.lag_ms)), int(p.get("hits", 0)))
		"on_error":
			var code := str(p.get("code", "unknown"))
			last_error = code
			if is_calibrating and code == "audio_locked":
				is_calibrating = false
				calibrated.emit(Session.lag_ms, 0)
			bridge_error.emit(code, str(p.get("msg", "")))


# --- Заглушка вне веба (как ?mock=perfect) -------------------------------------

func _load_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	return JSON.parse_string(FileAccess.get_file_as_string(path))


func _stub_load_song(id: String) -> void:
	var ref = _load_json(MOCK_DIR + id + ".reference.json")
	if not ref is Dictionary:
		ref = _load_json(MOCK_DIR + "demo.reference.json")
	if not ref is Dictionary:
		_dispatch("on_error", JSON.stringify({"code": "net", "msg": "song %s not found" % id}))
		return
	_stub.ref = ref
	_stub.state = "idle"
	var notes: Array = []
	for line in ref.get("lines", []):
		for n in line.get("notes", []):
			if n.get("type", "normal") != "free":
				notes.append({"i": n.i, "line": line.i, "type": n.get("type", "normal"),
					"midi": float(n.midi), "t": float(n.t), "end": float(n.t) + float(n.d)})
	notes.sort_custom(func(a: Dictionary, b: Dictionary) -> bool: return a.t < b.t)
	_stub.notes = notes
	var tol := {"easy": 200, "normal": 120, "hard": 60}
	var payload: Dictionary = ref.duplicate(true)
	payload["scoring"] = {"tol_cents": tol.get(Session.difficulty, 120)}
	payload["lag_ms"] = Session.lag_ms
	_emit_deferred.call_deferred("on_ready", JSON.stringify(payload))


func _stub_start() -> void:
	if (_stub.ref as Dictionary).is_empty():
		_dispatch("on_error", JSON.stringify({"code": "audio_locked", "msg": "start before load_song"}))
		return
	if _stub.state == "playing":
		return
	_stub.state = "playing"
	_stub.start_ms = Time.get_ticks_msec() + int(STUB_START_DELAY * 1000.0)
	_stub.last_t = -STUB_START_DELAY
	_stub.next_note = 0


func _stub_t() -> float:
	if _stub.state == "idle":
		return 0.0
	return (Time.get_ticks_msec() - int(_stub.start_ms)) / 1000.0


func _stub_poll() -> Dictionary:
	var t := _stub_t()
	var out: Array = []
	var lvl := 0.0
	if _stub.state == "playing":
		var k := floori(maxf(float(_stub.last_t), t - 2.0) / STUB_HOP) + 1
		while k * STUB_HOP <= t:
			var ft := k * STUB_HOP
			var note := _stub_note_at(ft)
			if note.is_empty():
				out.append({"t": snappedf(ft, 0.001), "hz": 0.0, "conf": 0.0, "rms": 0.004})
			else:
				var cents := randf_range(-30.0, 30.0)
				var hz := 440.0 * pow(2.0, (float(note.midi) + cents / 100.0 - 69.0) / 12.0)
				out.append({"t": snappedf(ft, 0.001), "hz": snappedf(hz, 0.1), "conf": 0.95, "rms": 0.05})
				lvl = 0.05
			k += 1
		_stub.last_t = t
		var notes: Array = _stub.notes
		while int(_stub.next_note) < notes.size() and t >= float(notes[_stub.next_note].end):
			var n: Dictionary = notes[_stub.next_note]
			_stub.next_note = int(_stub.next_note) + 1
			_emit_deferred.call_deferred("on_note_judged", JSON.stringify({"i": n.i, "line": n.line,
				"type": n.type, "hit": 0.95, "cents": randi_range(-10, 10), "onset_ms": randi_range(5, 40)}))
		var dur := float(_stub.ref.get("audio", {}).get("duration", 0.0))
		if t >= dur:
			_stub.state = "ended"
			_emit_deferred.call_deferred("on_song_end", JSON.stringify({"t": snappedf(t, 0.001)}))
	return {"t_now": snappedf(t, 0.001), "state": _stub.state, "level": lvl, "frames": out}


func _stub_note_at(t: float) -> Dictionary:
	for n: Dictionary in _stub.notes:
		if t >= n.t and t < n.end:
			return n
	return {}


func _stub_submit(player: String) -> void:
	await get_tree().create_timer(STUB_SUBMIT_DELAY).timeout
	var r = _load_json(MOCK_DIR + "result.perfect.json")
	if not r is Dictionary:
		_dispatch("on_error", JSON.stringify({"code": "net", "msg": "mock result not found"}))
		return
	if not player.is_empty():
		r["player"] = player
	r["client_id"] = STUB_CLIENT_ID
	# заглушка «записала» дубль: прослушивание без звука, только таймлайн
	_stub["review"] = {"dur": float(_stub.ref.get("audio", {}).get("duration", 10.0)),
		"song_id": str(_stub.ref.get("id", "demo")), "take_id": r.get("take_id"),
		"pos": 0.0, "playing": false, "start_ms": 0, "start_pos": 0.0}
	_dispatch("on_result", JSON.stringify(r))


func _stub_review_is_playing() -> bool:
	return _stub.has("review") and bool(_stub.review.playing)


func _stub_review_pos() -> float:
	var r: Dictionary = _stub.review
	if not bool(r.playing):
		return float(r.pos)
	return minf(float(r.dur), float(r.start_pos) + (Time.get_ticks_msec() - int(r.start_ms)) / 1000.0)


func _stub_review_play(from_sec: float) -> void:
	if not _stub.has("review") or _stub.state == "playing":
		return
	var r: Dictionary = _stub.review
	var pos := from_sec if from_sec >= 0.0 else _stub_review_pos()
	pos = clampf(pos, 0.0, float(r.dur))
	if pos >= float(r.dur) - 0.05:
		pos = 0.0
	r.pos = pos
	r.start_pos = pos
	r.start_ms = Time.get_ticks_msec()
	r.playing = true
