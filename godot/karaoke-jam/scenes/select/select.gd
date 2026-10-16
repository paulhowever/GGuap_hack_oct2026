extends Control
## Экран выбора песни: список из GET /api/v1/songs (в моке — демо-песня),
## выбор сложности (Session.difficulty), запуск игры. Esc / «Назад» — в меню.

const BOOT_SCENE := "res://scenes/boot/boot.tscn"
const GAME_SCENE := "res://scenes/game/game.tscn"

@onready var _status: Label = %Status
@onready var _list: VBoxContainer = %SongList
@onready var _retry: Button = %RetryButton
@onready var _diff_buttons := {"easy": %EasyButton, "normal": %NormalButton, "hard": %HardButton}

var _leaving: bool = false


func _ready() -> void:
	%BackButton.pressed.connect(_back)
	_retry.pressed.connect(_load_songs)
	var group := ButtonGroup.new()
	for d: String in _diff_buttons:
		var b: Button = _diff_buttons[d]
		b.button_group = group
		b.button_pressed = d == Session.difficulty
		b.pressed.connect(func() -> void:
			Session.difficulty = d
			Session.save_settings())
	MenuMusic.start()   # при возврате из игры музыка меню снова играет
	# Boot уходит в затемнение цветом Fade — появляемся из того же цвета,
	# иначе фон «выпрыгивает» резко.
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	_load_songs()


func _load_songs() -> void:
	_retry.visible = false
	_status.text = "Загружаем песни…"
	_status.visible = true
	for c in _list.get_children():
		c.queue_free()
	%BackButton.grab_focus.call_deferred()
	var r: Dictionary = await Api.get_songs()
	if not is_inside_tree():
		return
	if not r.ok:
		_status.text = "Не удалось получить список песен (%s). Проверьте, что сервер запущен." % r.error
		_retry.visible = true
		_retry.grab_focus.call_deferred()
		return
	var songs: Array = r.data
	if songs.is_empty():
		_status.text = "Песен пока нет."
		return
	_status.visible = r.get("mock", false)
	_status.text = "Сервер недоступен — демо-песня из мока."
	for s in songs:
		if s is Dictionary:
			_list.add_child(_make_song_button(s))
	(_list.get_child(0) as Button).grab_focus.call_deferred()


## Карточка песни: SongButton (без свечения — его обрезал бы ScrollContainer),
## две строки: название крупно и «Артист · 3:25 · ★★★» мельче.
func _make_song_button(song: Dictionary) -> Button:
	var b := Button.new()
	b.theme_type_variation = &"SongButton"
	b.custom_minimum_size = Vector2(0, 104)
	b.tooltip_text = str(song.get("title", ""))
	var dur := int(float(song.get("duration", 0.0)))
	var stars := "★".repeat(clampi(int(song.get("difficulty", 1)), 1, 5))

	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	box.offset_left = 32
	box.offset_right = -32
	box.alignment = BoxContainer.ALIGNMENT_CENTER
	box.add_theme_constant_override(&"separation", 2)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE

	var title := Label.new()
	title.text = str(song.get("title", "?"))
	title.add_theme_font_override(&"font", get_theme_font(&"font", &"Button"))
	title.add_theme_font_size_override(&"font_size", 30)
	title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	title.mouse_filter = Control.MOUSE_FILTER_IGNORE

	var sub := Label.new()
	sub.theme_type_variation = &"HintLabel"
	sub.add_theme_font_size_override(&"font_size", 20)
	sub.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	sub.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var parts: PackedStringArray = []
	if str(song.get("artist", "")) != "":
		parts.append(str(song.artist))
	@warning_ignore("integer_division")
	parts.append("%d:%02d" % [dur / 60, dur % 60])
	parts.append(stars)
	sub.text = "  ·  ".join(parts)

	box.add_child(title)
	box.add_child(sub)
	b.add_child(box)
	b.pressed.connect(_play.bind(song))
	return b


func _play(song: Dictionary) -> void:
	if _leaving:
		return
	_leaving = true
	Session.song_id = str(song.get("id", ""))
	Session.song_info = song
	Session.last_result = {}
	var tw := create_tween()
	tw.tween_property(%Fade, "modulate:a", 1.0, 0.35)
	await tw.finished
	get_tree().change_scene_to_file(GAME_SCENE)


func _back() -> void:
	if _leaving:
		return
	get_tree().change_scene_to_file(BOOT_SCENE)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		_back()
