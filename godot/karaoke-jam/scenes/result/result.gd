extends Control
## Экран результата: Session.last_result (контракт TakeResult).
## Итог, оценка, точность по высоте/ритму, разбор строк с советами,
## место в таблице (блок скрыт, если leaderboard == null), прослушивание дубля
## и «Опубликовать кавер» — в таблицу лидеров попадают только опубликованные (ADR-024).

const SELECT_SCENE := "res://scenes/select/select.tscn"
const GAME_SCENE := "res://scenes/game/game.tscn"
const MAX_SCORE := 10000.0
const FILL_SEC := 1.4
const S_SHADER := preload("res://ui/shaders/grade_s.gdshader")
## Доля font_size, которую занимает заглавная буква (типично 0.7–0.75).
const CAP_HEIGHT := 0.72
## Цвета рангов: S — золото, A..D — от голубого проекта к красному.
const GRADE_COLORS := {
	"S": Color(1.0, 0.82, 0.35),      # золото
	"A": Color(0.373, 0.827, 0.737),  # #5FD3BC
	"B": Color(0.85, 0.83, 0.36),     # жёлто-лаймовый
	"C": Color(1.0, 0.6, 0.25),       # оранжевый
	"D": Color(1.0, 0.365, 0.365),    # #FF5D5D
}

@onready var _ring: ScoreRing = %ScoreRing
@onready var _percent: Label = %PercentLabel
@onready var _total: Label = %TotalLabel
@onready var _grade: Label = %GradeLabel
## «Удары» ранга под бит музыки меню (включается после появления ранга).
@onready var _grade_beat: BeatReactor = %GradeBeat
@onready var _details: Label = %DetailsLabel
@onready var _lines: VBoxContainer = %LinesList
@onready var _board: Label = %BoardLabel
@onready var _warn: Label = %WarnLabel

@onready var _player: Control = %Player
@onready var _play: Button = %PlayButton
@onready var _seek: HSlider = %Seek
@onready var _time: Label = %TimeLabel
@onready var _player_hint: Label = %PlayerHint
@onready var _publish: Button = %PublishButton
@onready var _publish_hint: Label = %PublishHint

const PUBLISH_TEXT := "Опубликовать кавер"  # подпись кнопки в покое
const CONFIRM_SCENE := preload("res://ui/panels/confirm_panel.tscn")

var _leaving: bool = false
var _publishing: bool = false
var _confirm: ConfirmPanel
## Дубль этого результата ещё в памяти страницы — можно послушать.
var _can_review: bool = false
var _review_state: String = "idle"
var _seeking: bool = false


func _ready() -> void:
	%AgainButton.pressed.connect(_go.bind(GAME_SCENE))
	%SelectButton.pressed.connect(_go.bind(SELECT_SCENE))
	%AgainButton.grab_focus.call_deferred()
	if Session.result_review:
		var song := str(Session.song_info.get("title", Session.last_result.get("song_id", "")))
		%Title.text = "Мой последний результат" + (" — %s" % song if not song.is_empty() else "")
		%AgainButton.text = "Спеть эту песню"
	MenuMusic.start()   # музыка меню задаёт бит для ударов ранга
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	# после пения персонажи уже на месте; «Мой последний результат» — выезжают
	Performers.enter()
	Performers.dim(false)
	_fill(Session.last_result)
	_setup_review()
	_confirm = CONFIRM_SCENE.instantiate()
	add_child(_confirm)
	_setup_publish()


func _exit_tree() -> void:
	if _can_review:
		VoiceBridge.review_stop()
		if _review_state == "playing":
			MenuMusic.duck(false)


# --- Прослушивание своего дубля (голос + минус) ----------------------------------

func _setup_review() -> void:
	var st := VoiceBridge.review_state()
	var take_id = Session.last_result.get("take_id")
	# дубль в JS — от последнего пения; сверяем, что он от этого же результата
	_can_review = bool(st.get("available", false)) and (st.get("take_id") == null or take_id == null
		or str(st.get("take_id")) == str(take_id))
	_player.visible = true
	_player_hint.visible = not _can_review
	if not _can_review:
		_player.modulate.a = 0.45
		_play.disabled = true
		_seek.editable = false
		_player_hint.text = "Запись хранится только до перезагрузки страницы — спойте ещё раз, чтобы послушать себя."
		return
	_seek.max_value = maxf(float(st.get("duration", 0.0)), 0.01)
	_play.pressed.connect(_toggle_play)
	_seek.drag_started.connect(func() -> void: _seeking = true)
	_seek.drag_ended.connect(func(_changed: bool) -> void:
		_seeking = false
		VoiceBridge.review_seek(_seek.value))
	# клик по полосе без перетаскивания тоже перематывает
	_seek.value_changed.connect(func(v: float) -> void:
		if not _seeking and absf(v - float(VoiceBridge.review_state().get("t", 0.0))) > 0.25:
			VoiceBridge.review_seek(v))
	_update_player(st)


func _toggle_play() -> void:
	if _review_state == "playing":
		VoiceBridge.review_pause()
		MenuMusic.duck(false)
		_grade_beat.enabled = true
	else:
		MenuMusic.duck(true)   # музыка меню не мешает слушать
		_grade_beat.enabled = false
		VoiceBridge.review_play()
	_update_player(VoiceBridge.review_state())


func _process(_delta: float) -> void:
	if _can_review:
		_update_player(VoiceBridge.review_state())


func _update_player(st: Dictionary) -> void:
	var t := float(st.get("t", 0.0))
	var dur := float(st.get("duration", 0.0))
	var state := str(st.get("state", "idle"))
	if state != _review_state:
		if _review_state == "playing" and state == "ended":
			MenuMusic.duck(false)
		_review_state = state
		_play.text = "❚❚  Пауза" if state == "playing" else "▶  Послушать"
	if not _seeking:
		_seek.set_value_no_signal(t)
	_time.text = "%s / %s" % [_fmt(_seek.value if _seeking else t), _fmt(dur)]


func _fmt(sec: float) -> String:
	return fmt_time(sec)


## «м:сс» для плееров (здесь и в окне кавера).
static func fmt_time(sec: float) -> String:
	var s := maxi(0, int(sec))
	@warning_ignore("integer_division")
	return "%d:%02d" % [s / 60, s % 60]


## «Высота N% · Ритм N% · Бонусы N%» из score контракта TakeResult.
static func details_text(score: Dictionary) -> String:
	return "Высота %d%%   ·   Ритм %d%%   ·   Бонусы %d%%" % [
		roundi(float(score.get("pitch_pct", 0))), roundi(float(score.get("rhythm_pct", 0))),
		roundi(float(score.get("extras_pct", 0)))]


## Строка разбора «текст — оценка (очки)» и совет под ней, если есть.
static func make_line_label(line: Dictionary) -> Label:
	var l := Label.new()
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.add_theme_font_size_override(&"font_size", 24)
	var tip = line.get("tip")
	l.text = "«%s» — %s (%d)%s" % [line.get("text", ""), line.get("grade", ""),
		int(line.get("score", 0)), ("\n   " + str(tip)) if tip != null and str(tip) != "" else ""]
	return l


func _fill(r: Dictionary) -> void:
	var score: Dictionary = r.get("score", {}) if r.get("score") is Dictionary else {}
	var total := clampi(int(score.get("total", 0)), 0, int(MAX_SCORE))
	_details.text = details_text(score)
	_animate_score(float(total), str(score.get("grade", "—")))

	for line in r.get("lines", []):
		if line is Dictionary:
			_lines.add_child(make_line_label(line))

	_show_board_place(r, false)

	var integrity = r.get("integrity")
	_warn.visible = integrity is Dictionary and str(integrity.get("status", "ok")) != "ok"
	if _warn.visible:
		_warn.text = "Этот дубль нельзя опубликовать в таблицу: проверка честности не пройдена."


## В таблице только опубликованные каверы (ADR-024): до публикации leaderboard —
## место, которое займёт этот дубль, после — место в таблице.
func _show_board_place(r: Dictionary, is_published: bool) -> void:
	var lb = r.get("leaderboard")
	_board.visible = lb is Dictionary
	if not lb is Dictionary:
		return
	var place := "Место %d из %d" % [int(lb.get("rank", 0)), int(lb.get("of", 0))]
	_board.text = (place + "  ·  кавер опубликован") if is_published \
		else ("%s при публикации%s" % [place, "  ·  личный рекорд!" if lb.get("personal_best", false) else ""])


# --- Публикация кавера ------------------------------------------------------------

## Кнопка только после настоящего пения, только для честного дубля и если движок умеет.
func _setup_publish() -> void:
	var r := Session.last_result
	var integrity = r.get("integrity")
	var ok := not (integrity is Dictionary) or str(integrity.get("status", "ok")) == "ok"
	_publish.visible = not Session.result_review and ok and r.get("take_id") != null \
		and VoiceBridge.has_covers()
	_publish_hint.visible = false
	if _publish.visible:
		_publish.pressed.connect(_on_publish_pressed)


func _on_publish_pressed() -> void:
	if _publishing:
		return
	_publishing = true
	_publish.disabled = true
	var r := Session.last_result
	var take_id := str(r.get("take_id"))
	var total := int((r.get("score", {}) as Dictionary).get("total", 0)) if r.get("score") is Dictionary else 0
	var song_id := str(r.get("song_id", Session.song_id))
	var difficulty := str(r.get("difficulty", Session.difficulty))
	_publish.text = "Проверяем таблицу…"
	var board: Dictionary = await Api.get_leaderboard(song_id, difficulty, 100)
	if not is_inside_tree():
		return
	var ask := _publish_question(board, take_id, total)
	_publish.text = PUBLISH_TEXT
	if ask.is_empty():   # этот дубль уже в таблице
		_published_done(board)
		return
	var yes: bool = await _confirm.ask(ask.title, ask.text, "Опубликовать")
	if not is_inside_tree():
		return
	if not yes:
		_publishing = false
		_publish.disabled = false
		_publish.grab_focus()
		return
	_publish.text = "Публикуем…"
	_publish_hint.visible = false
	VoiceBridge.publish(take_id)
	var res: Array = await published_for(take_id)
	if not is_inside_tree():
		return
	if bool(res[0]):
		var fresh: Dictionary = await Api.get_leaderboard(song_id, difficulty, 100)
		if is_inside_tree():
			_published_done(fresh)
		return
	_publishing = false
	_publish.disabled = false
	_publish.text = PUBLISH_TEXT
	_publish_hint.text = publish_error_text(str(res[1]))
	_publish_hint.visible = true


## Ждёт ответ моста именно для этого дубля: [ok, code].
static func published_for(take_id: String) -> Array:
	while true:
		# await сигнала с несколькими аргументами отдаёт их массивом
		var a: Array = await VoiceBridge.published
		if str(a[0]) == take_id:
			return [a[2], a[3]]
	return [false, "unknown"]


## Текст подтверждения: что сейчас в таблице и каким будет новое место.
## Пусто — этот дубль уже опубликован.
func _publish_question(board: Dictionary, take_id: String, total: int) -> Dictionary:
	var privacy := "Запись голоса станет доступна всем: её можно будет послушать из таблицы лидеров."
	if not board.get("ok", false) or not board.get("data") is Array:
		return {"title": "Опубликовать кавер?", "text": privacy}
	var rows: Array = board.data
	var mine: Dictionary = {}
	var others := 0
	var ahead := 0
	for row in rows:
		if not row is Dictionary:
			continue
		if bool(row.get("me", false)):
			mine = row
			continue
		others += 1
		if int(row.get("total", 0)) >= total:
			ahead += 1
	if not mine.is_empty() and str(mine.get("take_id")) == take_id:
		return {}
	var new_place := "Новый дубль: %d очков, место %d из %d." % [total, ahead + 1, others + 1]
	if mine.is_empty():
		return {"title": "Опубликовать кавер?", "text": "%s\n%s" % [new_place, privacy]}
	var old_place := "Сейчас в таблице ваш кавер: %d очков, место %d из %d." % [
		int(mine.get("total", 0)), int(mine.get("rank", 0)), rows.size()]
	if int(mine.get("total", 0)) > total:
		return {"title": "Новый кавер хуже текущего",
			"text": "%s\n%s\nОн заменит текущий, и ваша строка в таблице опустится." % [old_place, new_place]}
	return {"title": "Заменить кавер в таблице?",
		"text": "%s\n%s\nПрежний кавер снимется с публикации." % [old_place, new_place]}


func _published_done(board: Dictionary) -> void:
	_publishing = false
	_publish.disabled = true
	_publish.text = "Опубликовано ✓"
	_publish_hint.visible = false
	if board.get("ok", false) and board.get("data") is Array:
		for row in board.data:
			if row is Dictionary and bool(row.get("me", false)):
				_board.visible = true
				_board.text = "Место %d из %d  ·  кавер опубликован" % [int(row.get("rank", 0)), (board.data as Array).size()]
				return
	_show_board_place(Session.last_result, true)


## Понятный текст ошибки publish/unpublish по коду моста или бэкенда.
static func publish_error_text(code: String) -> String:
	match code:
		"not_owner":
			return "Это не ваш дубль — опубликовать его нельзя."
		"take_not_ok":
			return "Дубль не прошёл проверку честности."
		"take_not_found", "not_published":
			return "Дубль не найден на сервере."
		"audio_not_found":
			return "Запись дубля не сохранилась на сервере."
		"net":
			return "Нет связи с сервером. Попробуйте ещё раз."
		"unsupported":
			return "Эта версия страницы не умеет публиковать — обновите её."
	return "Не получилось (%s). Попробуйте ещё раз." % code


## Кольцо заполняется до процента, процент и очки «набегают»,
## затем ранг появляется с «попом».
func _animate_score(total: float, grade: String) -> void:
	_ring.value = 0.0
	_set_progress(0.0, total)
	_grade.text = grade
	_grade.modulate.a = 0.0
	_style_grade(grade)
	_grade_beat.enabled = false
	var tw := create_tween()
	tw.tween_method(_set_progress.bind(total), 0.0, 1.0, FILL_SEC) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_callback(_pop_grade)


## S — статичный золотой градиент (шейдер), остальные ранги — сплошной цвет.
func _style_grade(grade: String) -> void:
	if grade == "S":
		var mat := ShaderMaterial.new()
		mat.shader = S_SHADER
		_grade.material = mat
		_grade.add_theme_color_override(&"font_color", Color.WHITE)
	else:
		_grade.material = null
		_grade.add_theme_color_override(&"font_color", GRADE_COLORS.get(grade, Color.WHITE))


## Растягивает градиент S ровно по высоте заглавной буквы (а не всей строки
## с пустыми ascent/descent), иначе перепад цвета почти не виден.
func _fit_grade_gradient() -> void:
	var mat := _grade.material as ShaderMaterial
	if mat == null:
		return
	var font := _grade.get_theme_font(&"font")
	var fs := _grade.get_theme_font_size(&"font_size")
	var text_h := font.get_height(fs)
	# смещение строки внутри Label с учётом вертикального выравнивания
	var top := (_grade.size.y - text_h) * (float(_grade.vertical_alignment) * 0.5) \
		if _grade.vertical_alignment != VERTICAL_ALIGNMENT_FILL else 0.0
	var baseline := top + font.get_ascent(fs)
	mat.set_shader_parameter(&"grad_top", baseline - fs * CAP_HEIGHT)
	mat.set_shader_parameter(&"grad_bottom", baseline)


func _set_progress(k: float, total: float) -> void:
	var pts := total * k
	_ring.value = pts / MAX_SCORE * 100.0
	_percent.text = "%.1f%%" % _ring.value
	_total.text = "%d очков" % roundi(pts)


## «Поп» ранга; после него масштабом управляет BeatReactor (удары под бит).
func _pop_grade() -> void:
	_grade.pivot_offset = _grade.size * 0.5
	_fit_grade_gradient()   # к этому моменту раскладка Label уже посчитана
	_grade.scale = Vector2.ONE * 1.6
	var tw := create_tween().set_parallel()
	tw.tween_property(_grade, "modulate:a", 1.0, 0.2)
	tw.tween_property(_grade, "scale", Vector2.ONE, 0.35) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.chain().tween_callback(func() -> void: _grade_beat.enabled = _review_state != "playing")


func _go(scene: String) -> void:
	if _leaving:
		return
	_leaving = true
	# «Спеть ещё раз» / «Спеть эту песню» — персонажи остаются, иначе уезжают
	Performers.dim(true)
	if scene != GAME_SCENE:
		Performers.leave()
	var tw := create_tween()
	tw.tween_property(%Fade, "modulate:a", 1.0, 0.3)
	await tw.finished
	get_tree().change_scene_to_file(scene)


func _unhandled_input(event: InputEvent) -> void:
	if _confirm and _confirm.is_open:
		return   # Esc закрывает диалог подтверждения, а не экран
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		_go(SELECT_SCENE)
