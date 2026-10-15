extends Control
## Игровой экран: load_song → on_ready → start; дорожка нот, след голоса, текст,
## оценки нот (on_note_judged) и примерный живой счёт. Конец песни → submit →
## on_result → экран результата. Esc — остановить и выйти к выбору песни.
## Единственные часы — VoiceBridge.t_now (часы минуса в JS).

const SELECT_SCENE := "res://scenes/select/select.tscn"
const RESULT_SCENE := "res://scenes/result/result.tscn"
const MAX_SCORE := 10000.0
const WEIGHTS := {"normal": 1.0, "golden": 2.0, "rap": 1.0, "rap_golden": 2.0, "free": 0.0}
const C_SUNG := Color(1.0, 0.478, 0.239)

enum Phase { LOADING, PLAYING, SUBMITTING, ERROR, LEAVING }

@onready var _lane: NoteLane = %NoteLane
@onready var _title: Label = %SongTitle
@onready var _score: Label = %ScoreLabel
@onready var _lyrics: RichTextLabel = %Lyrics
@onready var _next_lyrics: Label = %NextLyrics
@onready var _status: Label = %StatusLabel
@onready var _judge: Label = %JudgeLabel
@onready var _progress: ProgressBar = %SongProgress
@onready var _error_box: Control = %ErrorBox
@onready var _error_text: Label = %ErrorText
@onready var _retry: Button = %RetryButton
@onready var _exit: Button = %ExitButton

var _phase: Phase = Phase.LOADING
var _lines: Array = []
var _duration: float = 0.0
var _point_per_weight: float = 0.0
var _note_weight: Dictionary = {}
var _live_score: float = 0.0
var _shown_score: float = 0.0
var _line_idx: int = -2
var _can_resubmit: bool = false
var _judge_tween: Tween


func _ready() -> void:
	MenuMusic.stop()
	_error_box.visible = false
	_judge.modulate.a = 0.0
	_title.text = str(Session.song_info.get("title", Session.song_id))
	_score.text = "0"
	_lyrics.text = ""
	_next_lyrics.text = ""
	_retry.pressed.connect(_on_retry)
	_exit.pressed.connect(_leave.bind(SELECT_SCENE))
	VoiceBridge.song_ready.connect(_on_song_ready)
	VoiceBridge.note_judged.connect(_on_note_judged)
	VoiceBridge.song_ended.connect(_on_song_ended)
	VoiceBridge.result_received.connect(_on_result)
	VoiceBridge.bridge_error.connect(_on_bridge_error)
	VoiceBridge.polled.connect(_on_polled)
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	if Session.song_id.is_empty():
		_show_error("Песня не выбрана.", false)
		return
	_set_status("Загружаем песню…")
	VoiceBridge.load_song(Session.song_id)


func _exit_tree() -> void:
	if _phase == Phase.PLAYING:
		VoiceBridge.stop()


# --- События моста ------------------------------------------------------------

func _on_song_ready(ref: Dictionary) -> void:
	if _phase != Phase.LOADING:
		return
	_lines = ref.get("lines", [])
	_duration = float(ref.get("audio", {}).get("duration", 0.0))
	_title.text = "%s — %s" % [ref.get("title", "?"), ref.get("artist", "")]
	_lane.set_reference(ref)
	var total := 0.0
	for line in _lines:
		for n in line.get("notes", []):
			var w: float = WEIGHTS.get(str(n.get("type", "normal")), 1.0)
			_note_weight[int(n.i)] = w
			total += w
	_point_per_weight = MAX_SCORE / total if total > 0.0 else 0.0
	_set_status("")
	_phase = Phase.PLAYING
	VoiceBridge.start()


func _on_polled() -> void:
	if _phase != Phase.PLAYING:
		return
	var t := VoiceBridge.t_now
	_lane.push_frames(VoiceBridge.frames, t)
	if _duration > 0.0:
		_progress.value = clampf(t / _duration, 0.0, 1.0)
	_update_lyrics(t)


func _on_note_judged(v: Dictionary) -> void:
	if _phase != Phase.PLAYING:
		return
	var i := int(v.get("i", -1))
	var hit := clampf(float(v.get("hit", 0.0)), 0.0, 1.0)
	_lane.judge(i, hit)
	_live_score += _point_per_weight * float(_note_weight.get(i, 1.0)) * hit
	_show_judgement(hit, int(v.get("onset_ms", 0)))


func _on_song_ended(_t: float) -> void:
	if _phase == Phase.PLAYING:
		_submit()


func _on_result(result: Dictionary) -> void:
	if _phase != Phase.SUBMITTING:
		return
	Session.last_result = result
	_leave(RESULT_SCENE)


func _on_bridge_error(code: String, msg: String) -> void:
	match _phase:
		Phase.LOADING:
			var text := "Не удалось загрузить песню."
			if code == "decode_failed":
				text = "Не удалось раскодировать музыку песни."
			elif code == "audio_locked":
				text = "Звук заблокирован браузером. Обновите страницу и нажмите «Начать»."
			_show_error("%s (%s)" % [text, code], false)
		Phase.SUBMITTING:
			var text := "Не удалось отправить запись на оценку."
			if code == "net":
				text = "Нет связи с сервером — запись не отправлена."
			_show_error("%s (%s)" % [text, code], true)
		_:
			push_warning("Game: ошибка моста %s: %s" % [code, msg])


# --- Логика -----------------------------------------------------------------------

func _submit() -> void:
	_phase = Phase.SUBMITTING
	_error_box.visible = false
	_set_status("Подсчитываем результат…")
	VoiceBridge.submit(Session.nickname, Session.challenge_id)


func _on_retry() -> void:
	if _phase == Phase.ERROR and _can_resubmit:
		_submit()


func _show_error(text: String, can_retry: bool) -> void:
	_phase = Phase.ERROR
	_can_resubmit = can_retry
	_set_status("")
	_error_text.text = text
	_retry.visible = can_retry
	_error_box.visible = true
	(_retry if can_retry else _exit).grab_focus.call_deferred()


func _set_status(text: String) -> void:
	_status.text = text
	_status.visible = not text.is_empty()


func _update_lyrics(t: float) -> void:
	# текущая строка — последняя начавшаяся (с упреждением 1 с);
	# после её конца (+0.5 с) показываем следующую
	var idx := -1
	for k in _lines.size():
		if t >= float(_lines[k].t0) - 1.0:
			idx = k
	if idx >= 0 and t > float(_lines[idx].t1) + 0.5 and idx + 1 < _lines.size():
		idx += 1
	if idx < 0 and not _lines.is_empty():
		idx = 0
	if idx != _line_idx:
		_line_idx = idx
		var nxt := idx + 1
		_next_lyrics.text = str(_lines[nxt].text) if nxt > 0 and nxt < _lines.size() else ""
	if idx < 0:
		_lyrics.text = ""
		return
	var sung := ""
	var rest := ""
	for n in _lines[idx].get("notes", []):
		var syl := str(n.get("syl", ""))
		if t >= float(n.t):
			sung += syl
		else:
			rest += syl
	_lyrics.text = "[center][color=#%s]%s[/color]%s[/center]" % [C_SUNG.to_html(false), _esc(sung), _esc(rest)]


func _esc(s: String) -> String:
	return s.replace("[", "[lb]")


func _show_judgement(hit: float, onset_ms: int) -> void:
	var text := "Мимо"
	var col := Color(1.0, 0.365, 0.365)
	if hit >= 0.9:
		text = "Отлично!"
		col = Color(0.373, 0.827, 0.737)
	elif hit >= 0.7:
		text = "Хорошо"
		col = Color(0.6, 0.85, 0.45)
	elif hit >= 0.4:
		text = "Неплохо"
		col = Color(1.0, 0.8, 0.25)
	if hit >= 0.4 and absi(onset_ms) >= 100:
		text += "  (поздно)" if onset_ms > 0 else "  (рано)"
	_judge.text = text
	_judge.add_theme_color_override(&"font_color", col)
	if _judge_tween and _judge_tween.is_valid():
		_judge_tween.kill()
	_judge.modulate.a = 1.0
	_judge.pivot_offset = _judge.size * 0.5
	_judge.scale = Vector2.ONE * 1.25
	_judge_tween = create_tween().set_parallel()
	_judge_tween.tween_property(_judge, "scale", Vector2.ONE, 0.15)
	_judge_tween.tween_property(_judge, "modulate:a", 0.0, 0.5).set_delay(0.6)


func _process(delta: float) -> void:
	if absf(_shown_score - _live_score) > 0.5:
		_shown_score = lerpf(_shown_score, _live_score, minf(1.0, delta * 8.0))
		_score.text = str(roundi(_shown_score))


func _leave(scene: String) -> void:
	if _phase == Phase.LEAVING:
		return
	if _phase == Phase.PLAYING:
		VoiceBridge.stop()
	_phase = Phase.LEAVING
	var tw := create_tween()
	tw.tween_property(%Fade, "modulate:a", 1.0, 0.3)
	await tw.finished
	get_tree().change_scene_to_file(scene)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		if _phase != Phase.SUBMITTING:
			_leave(SELECT_SCENE)

