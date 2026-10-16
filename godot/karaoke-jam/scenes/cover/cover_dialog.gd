class_name CoverDialog
extends ModalPanel
## Окно кавера из таблицы лидеров (ADR-024): персонаж автора в его наряде (avatar.outfit),
## ник полностью, очки и ранг, «О себе», плеер (вокал поверх минуса: ▶/❚❚ и перемотка,
## как на экране результата), подробности ранга и комментарии по строкам из GET /takes/{id}.
## У своей строки — «Снять публикацию».
## open_row(row) — строка лидерборда {rank, player, avatar, bio, total, grade, take_id, me, …}.

## Публикацию сняли — таблицу нужно перезагрузить.
signal unpublished(take_id: String)

const ResultScene := preload("res://scenes/result/result.gd")
const CONFIRM_SCENE := preload("res://ui/panels/confirm_panel.tscn")
const PREVIEW_SCENE := preload("res://ui/components/character_preview.tscn")
## Сколько отрисованных кадров держать окно видимым при прогреве шейдеров.
const WARM_UP_FRAMES := 3

@onready var _character_slot: Control = %Character
@onready var _bio_caption: Label = %BioCaption
@onready var _bio: Label = %CoverBio
@onready var _name: Label = %CoverName
@onready var _meta: Label = %CoverMeta
@onready var _grade: Label = %CoverGrade
@onready var _play: Button = %CoverPlay
@onready var _seek: HSlider = %CoverSeek
@onready var _time: Label = %CoverTime
@onready var _hint: Label = %CoverHint
@onready var _details: Label = %CoverDetails
@onready var _lines: VBoxContainer = %CoverLines
@onready var _unpublish: Button = %UnpublishButton
@onready var _close: Button = %CloseButton

var _row: Dictionary = {}
var _take_id: String = ""
## idle (не начато / закончилось) | loading | playing | paused
var _state: String = "idle"
var _duration: float = 0.0
var _seeking: bool = false
var _ducked: bool = false
var _seq: int = 0  # отменяет устаревшие загрузки подробностей
var _confirm: ConfirmPanel
## Персонаж автора: свой экземпляр превью, наряд задаётся из строки, а не из Session.
var _preview: CharacterPreview
var _outfit: CharacterOutfit
var _warming: bool = false


func _ready() -> void:
	super._ready()
	_confirm = CONFIRM_SCENE.instantiate()
	add_child(_confirm)
	_build_preview()
	_play.pressed.connect(_toggle_play)
	_close.pressed.connect(close)
	_unpublish.pressed.connect(_on_unpublish)
	_seek.drag_started.connect(func() -> void: _seeking = true)
	_seek.drag_ended.connect(func(_changed: bool) -> void:
		_seeking = false
		VoiceBridge.listen_seek(_seek.value))
	# клик по полосе без перетаскивания тоже перематывает
	_seek.value_changed.connect(func(v: float) -> void:
		if not _seeking and _state in ["playing", "paused"] \
				and absf(v - float(VoiceBridge.listen_state().get("t", 0.0))) > 0.25:
			VoiceBridge.listen_seek(v))
	VoiceBridge.listen_started.connect(_on_listen_started)
	VoiceBridge.listen_ended.connect(_on_listen_ended)
	set_process(false)


func open_row(row: Dictionary) -> void:
	if _warming:
		return
	_row = row
	_take_id = str(row.get("take_id", ""))
	_seq += 1
	_name.text = str(row.get("player", "?")) + ("  (вы)" if bool(row.get("me", false)) else "")
	_outfit.apply_outfit(outfit_of(row.get("avatar")))
	var bio := str(row.get("bio", "")).strip_edges() if row.get("bio") is String else ""
	_bio.text = bio
	_bio.visible = not bio.is_empty()
	_bio_caption.visible = not bio.is_empty()
	_preview.set_active(true)
	_preview.yaw = _preview.rest_yaw
	_meta.text = "Место %d   ·   %d очков" % [int(row.get("rank", 0)), int(row.get("total", 0))]
	var grade := str(row.get("grade", "—"))
	_grade.text = grade
	_grade.add_theme_color_override(&"font_color", ResultScene.GRADE_COLORS.get(grade, Color.WHITE))
	_unpublish.visible = bool(row.get("me", false)) and VoiceBridge.has_covers()
	_unpublish.disabled = false
	_unpublish.text = "Снять публикацию"
	_set_state("idle")
	_duration = 0.0
	_seek.max_value = 1.0
	_seek.set_value_no_signal(0.0)
	_time.text = "0:00 / 0:00"
	_hint.visible = false
	_play.disabled = not VoiceBridge.has_covers()
	open()
	_load_details(_seq)


# --- Персонаж автора ---------------------------------------------------------------

## Превью создаётся в коде: CharacterOutfit нужно выключить follow_session до его _ready,
## иначе он наденет на автора наряд текущего игрока и будет следить за гардеробом.
func _build_preview() -> void:
	_preview = PREVIEW_SCENE.instantiate()
	_preview.name = "AuthorPreview"
	_outfit = _preview.get_node("SubViewport/GV_Anim_Pack_1/Outfit") as CharacterOutfit
	_outfit.follow_session = false
	_character_slot.add_child(_preview)
	_preview.set_active(false)


## avatar из строки ({outfit: {slot: item_id}} или null) → наряд для apply_outfit.
static func outfit_of(avatar: Variant) -> Dictionary:
	if not avatar is Dictionary or not avatar.get("outfit") is Dictionary:
		return {}
	var out := {}
	var o: Dictionary = avatar.outfit
	for slot: Variant in o:
		var item := str(o[slot])
		if not item.is_empty() and ItemCatalog.get_default().find(StringName(item)) != null:
			out[StringName(str(slot))] = StringName(item)
	return out


## Прогрев шейдеров: окно на несколько кадров видимо, но прозрачно, а персонаж в нём —
## в полном наряде (по предмету на слот). WebGL компилирует шейдеры сейчас, а не на
## первом клике по строке. Вызывать, пока экран закрыт затемнением.
func warm_up() -> void:
	if is_open or visible or _warming:
		return
	_warming = true
	var full := {}
	for def: ItemDef in ItemCatalog.get_default().items:
		if def and def.scene and not full.has(def.slot):
			full[def.slot] = def.id
	_outfit.apply_outfit(full)
	modulate.a = 0.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	visible = true
	_preview.set_active(true)
	for i in WARM_UP_FRAMES:
		await RenderingServer.frame_post_draw
	if not is_inside_tree():
		return
	_preview.set_active(false)
	_outfit.apply_outfit({})
	visible = false
	modulate.a = 1.0
	mouse_filter = Control.MOUSE_FILTER_STOP
	_warming = false


# --- Подробности ранга и комментарии ---------------------------------------------

func _load_details(seq: int) -> void:
	_details.text = "Загружаем подробности…"
	for c in _lines.get_children():
		c.queue_free()
	var r: Dictionary = await Api.get_take(_take_id)
	if not is_inside_tree() or seq != _seq:
		return
	if not r.ok or not r.data is Dictionary:
		_details.text = "Подробности недоступны (%s)." % r.error
		return
	var take: Dictionary = r.data
	var score: Dictionary = take.get("score", {}) if take.get("score") is Dictionary else {}
	_details.text = ResultScene.details_text(score)
	for line in take.get("lines", []):
		if line is Dictionary:
			_lines.add_child(ResultScene.make_line_label(line))
	if _lines.get_child_count() == 0:
		var l := Label.new()
		l.theme_type_variation = &"HintLabel"
		l.text = "Комментариев к строкам нет."
		_lines.add_child(l)


# --- Плеер ------------------------------------------------------------------------

func _toggle_play() -> void:
	match _state:
		"playing":
			VoiceBridge.listen_pause()
			_set_state("paused")
		"paused":
			_duck(true)
			VoiceBridge.listen_resume()
			_set_state("playing")
		"idle":
			_hint.visible = false
			_duck(true)   # музыка меню не мешает слушать
			_set_state("loading")
			VoiceBridge.listen(_take_id)


func _on_listen_started(take_id: String, duration: float) -> void:
	if not is_open or take_id != _take_id or _state != "loading":
		return
	_duration = duration
	_seek.max_value = maxf(duration, 0.01)
	_set_state("playing")


func _on_listen_ended(take_id: String, reason: String, code: String) -> void:
	if not is_open or take_id != _take_id or _state == "idle":
		return
	_set_state("idle")
	_seek.set_value_no_signal(0.0)
	_time.text = "0:00 / %s" % ResultScene.fmt_time(_duration)
	if reason == "error":
		_hint.text = _listen_error_text(code)
		_hint.visible = true


func _process(_delta: float) -> void:
	var st: Dictionary = VoiceBridge.listen_state()
	if str(st.get("take_id", "")) != _take_id:
		return
	var t := float(st.get("t", 0.0))
	if not _seeking:
		_seek.set_value_no_signal(t)
	_time.text = "%s / %s" % [ResultScene.fmt_time(_seek.value if _seeking else t), ResultScene.fmt_time(_duration)]


func _set_state(state: String) -> void:
	_state = state
	set_process(state == "playing" or state == "paused")
	_seek.editable = state == "playing" or state == "paused"
	match state:
		"playing":
			ResultScene.set_play_button(_play, true)
		"loading":
			_play.icon = null
			_play.text = "Загружаем…"
		_:
			ResultScene.set_play_button(_play, false)
	_play.disabled = state == "loading"
	if state == "idle" or state == "paused":
		_duck(false)


func _duck(on: bool) -> void:
	if on == _ducked:
		return
	_ducked = on
	MenuMusic.duck(on)


static func _listen_error_text(code: String) -> String:
	match code:
		"audio_locked":
			return "Звук ещё не включён — нажмите на страницу и попробуйте снова."
		"not_published":
			return "Автор снял кавер с публикации."
		"net":
			return "Нет связи с сервером. Попробуйте ещё раз."
		"decode_failed":
			return "Не удалось прочитать запись."
		"unsupported":
			return "Эта версия страницы не умеет проигрывать каверы — обновите её."
	return "Не получилось воспроизвести (%s)." % code


# --- Снять публикацию -------------------------------------------------------------

func _on_unpublish() -> void:
	var yes: bool = await _confirm.ask("Снять кавер с публикации?",
		"Ваша строка исчезнет из таблицы лидеров, запись больше нельзя будет послушать.\n"
		+ "Опубликовать снова можно только сразу после пения.", "Снять")
	if not yes or not is_open:
		return
	if _state != "idle":
		VoiceBridge.listen_stop()
	_unpublish.disabled = true
	_unpublish.text = "Снимаем…"
	var take_id := _take_id
	VoiceBridge.unpublish(take_id)
	var res: Array = await ResultScene.published_for(take_id)
	if not is_inside_tree() or take_id != _take_id:
		return
	if bool(res[0]):
		unpublished.emit(take_id)
		close()
		return
	_unpublish.disabled = false
	_unpublish.text = "Снять публикацию"
	_hint.text = ResultScene.publish_error_text(str(res[1]))
	_hint.visible = true


# --- Закрытие ----------------------------------------------------------------------

func _on_closing() -> void:
	_seq += 1
	_preview.set_active(false)
	if _state != "idle":
		VoiceBridge.listen_stop()
	_set_state("idle")
	_duck(false)
	if _confirm.is_open:
		_confirm.close()


func _exit_tree() -> void:
	if _state != "idle":
		VoiceBridge.listen_stop()
	_duck(false)


func _unhandled_input(event: InputEvent) -> void:
	if _confirm and _confirm.is_open:
		return   # Esc закрывает сначала подтверждение
	super._unhandled_input(event)
