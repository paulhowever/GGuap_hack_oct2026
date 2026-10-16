extends Control
## Экран выбора песни: список из GET /api/v1/songs (в моке — демо-песня).
## Клик по карточке выбирает песню: список уезжает влево, справа выезжает
## таблица лидеров этой песни (GET /leaderboard/{id}, 20 строк) с выбором
## сложности (Session.difficulty) и кнопкой «Начать». Повторный клик по выбранной
## карточке (или Esc) снимает выбор — таблица уезжает, список возвращается в центр.
## «Мой последний результат» открывает сохранённый результат (Session.saved_result).
## В таблице только опубликованные каверы (ADR-024); клик по строке открывает окно кавера
## (CoverDialog: прослушивание, подробности ранга, комментарии, «Снять публикацию» у своей).
## Esc без выбора / «Назад» — в меню.

const BOOT_SCENE := "res://scenes/boot/boot.tscn"
const GAME_SCENE := "res://scenes/game/game.tscn"
const RESULT_SCENE := "res://scenes/result/result.tscn"
const COVER_SCENE := preload("res://scenes/cover/cover_dialog.tscn")
const ICON_STAR := preload("res://ui/icons/star.svg")
const ICON_NOTE := preload("res://ui/icons/note_single.svg")
const GRADE_COLORS: Dictionary = preload("res://scenes/result/result.gd").GRADE_COLORS
const C_ACCENT := Color(1.0, 0.478, 0.239)
const C_TEAL := Color(0.373, 0.827, 0.737)
const C_ROW := Color(0.227, 0.192, 0.251, 0.55)
const GAP := 40.0
const SLIDE_SEC := 0.4
## Ширины колонок таблицы: место, очки, ранг (ник занимает остальное).
const COL_RANK := 52.0
const COL_TOTAL := 110.0
const COL_GRADE := 60.0
## Кегль ячеек таблицы и заголовка: ник до 24 символов должен влезать целиком.
const CELL_FONT := 21
const HEADER_FONT := 18
## Внутренние поля строки таблицы слева/справа.
const ROW_PAD_L := 8.0
const ROW_PAD_R := 12.0

@onready var _stage: Control = %Stage
@onready var _song_card: Control = %SongCard
@onready var _board_card: Control = %BoardCard
@onready var _status: Label = %Status
@onready var _list: VBoxContainer = %SongList
@onready var _pick_hint: Label = %PickHint
@onready var _retry: Button = %RetryButton
@onready var _last_result: Button = %LastResultButton
@onready var _board_song: Label = %BoardSong
@onready var _board_list: VBoxContainer = %BoardList
@onready var _start: Button = %StartButton
@onready var _diff_buttons := {"easy": %EasyButton, "normal": %NormalButton, "hard": %HardButton}

var _leaving: bool = false
var _song_group := ButtonGroup.new()
## Выбранная песня (элемент /songs); пусто — ничего не выбрано.
var _selected: Dictionary = {}
var _board_open: bool = false
var _board_seq: int = 0
var _slide: Tween
var _header_style: StyleBoxFlat
var _cover: CoverDialog  # окно кавера (ModalPanel)
## Строка, с которой открыли окно кавера, — вернуть ей фокус после закрытия.
var _cover_from: Control


func _ready() -> void:
	%BackButton.pressed.connect(_back)
	_retry.pressed.connect(_load_songs)
	_last_result.pressed.connect(_open_last_result)
	_last_result.visible = Session.has_saved_result()
	_start.pressed.connect(func() -> void: _play(_selected))
	_song_group.allow_unpress = true
	var group := ButtonGroup.new()
	for d: String in _diff_buttons:
		var b: Button = _diff_buttons[d]
		b.button_group = group
		b.button_pressed = d == Session.difficulty
		b.pressed.connect(func() -> void:
			if Session.difficulty == d:
				return
			Session.difficulty = d
			Session.save_settings()
			_load_board())
	_build_board_header()
	_cover = COVER_SCENE.instantiate()
	add_child(_cover)
	move_child(_cover, %Fade.get_index())   # под затемнением перехода
	_cover.warm_up()   # пока экран под затемнением: шейдеры персонажа автора компилируются заранее
	_cover.unpublished.connect(func(_id: String) -> void: _load_board())
	_cover.closed.connect(func() -> void:
		if is_instance_valid(_cover_from) and _cover_from.is_inside_tree() and not _leaving:
			_cover_from.grab_focus.call_deferred())
	_stage.resized.connect(_layout)
	_song_card.minimum_size_changed.connect(_layout)
	_board_card.minimum_size_changed.connect(_layout)
	_layout()
	MenuMusic.start()   # при возврате из игры музыка меню снова играет
	# Boot уходит в затемнение цветом Fade — появляемся из того же цвета,
	# иначе фон «выпрыгивает» резко.
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	_load_songs()


# --- Раскладка и анимация карточек ------------------------------------------

func _centered_x() -> float:
	return (_stage.size.x - _song_card.size.x) * 0.5


## x карточек, когда таблица открыта: пара [список | таблица] по центру экрана.
func _pair_x() -> Vector2:
	var left := (_stage.size.x - (_song_card.size.x + GAP + _board_card.size.x)) * 0.5
	return Vector2(left, left + _song_card.size.x + GAP)


func _hidden_board_x() -> float:
	return _stage.size.x + GAP


## Мгновенная раскладка под текущее состояние (ресайз окна, смена высоты карточек).
func _layout() -> void:
	if _slide and _slide.is_valid():
		return   # идёт анимация — она сама приведёт карточки на место
	_song_card.reset_size()
	_board_card.reset_size()
	_song_card.position = Vector2(_pair_x().x if _board_open else _centered_x(),
		(_stage.size.y - _song_card.size.y) * 0.5)
	_board_card.position = Vector2(_pair_x().y if _board_open else _hidden_board_x(),
		(_stage.size.y - _board_card.size.y) * 0.5)


func _show_board(open: bool) -> void:
	if open == _board_open:
		return
	_board_open = open
	# подсказку гасим прозрачностью, а не visible: иначе карточка списка теряет
	# строку по высоте и при выборе песни прыгает вверх
	_pick_hint.modulate.a = 0.0 if open else 1.0
	if _slide and _slide.is_valid():
		_slide.kill()
	_song_card.reset_size()
	_board_card.reset_size()
	_board_card.position.y = (_stage.size.y - _board_card.size.y) * 0.5
	_song_card.position.y = (_stage.size.y - _song_card.size.y) * 0.5
	_slide = create_tween().set_parallel().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	if open:
		_board_card.visible = true
		if _board_card.modulate.a <= 0.01 or _board_card.position.x < _pair_x().y:
			_board_card.position.x = _hidden_board_x()
		_slide.tween_property(_song_card, "position:x", _pair_x().x, SLIDE_SEC)
		_slide.tween_property(_board_card, "position:x", _pair_x().y, SLIDE_SEC)
		_slide.tween_property(_board_card, "modulate:a", 1.0, SLIDE_SEC * 0.6)
	else:
		_slide.tween_property(_song_card, "position:x", _centered_x(), SLIDE_SEC)
		_slide.tween_property(_board_card, "position:x", _hidden_board_x(), SLIDE_SEC)
		_slide.tween_property(_board_card, "modulate:a", 0.0, SLIDE_SEC * 0.6)
		_slide.chain().tween_callback(func() -> void:
			if not _board_open:
				_board_card.visible = false)


# --- Список песен ----------------------------------------------------------------

func _load_songs() -> void:
	_retry.visible = false
	_status.text = "Загружаем песни…"
	_status.visible = true
	_pick_hint.visible = false
	_selected = {}
	_show_board(false)
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
	_pick_hint.visible = true
	for s in songs:
		if s is Dictionary:
			_list.add_child(_make_song_button(s))
	(_list.get_child(0) as Button).grab_focus.call_deferred()


## Карточка песни: SongButton (без свечения — его обрезал бы ScrollContainer),
## две строки: название крупно и «Артист · 3:25 · ★★★» мельче.
## Карточка — переключатель в общей группе: выбрана может быть только одна.
func _make_song_button(song: Dictionary) -> Button:
	var b := Button.new()
	b.theme_type_variation = &"SongButton"
	b.custom_minimum_size = Vector2(0, 104)
	b.tooltip_text = str(song.get("title", ""))
	b.toggle_mode = true
	b.button_group = _song_group
	b.set_meta(&"song", song)
	_style_selected(b)
	var dur := int(float(song.get("duration", 0.0)))
	var stars := clampi(int(song.get("difficulty", 1)), 1, 5)

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

	# «Артист · 3:25 · ★★★»: звёзды — значки (в Nunito нет ★, в вебе он не рисуется)
	var sub_row := HBoxContainer.new()
	sub_row.add_theme_constant_override(&"separation", 4)
	sub_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sub := Label.new()
	sub.theme_type_variation = &"HintLabel"
	sub.add_theme_font_size_override(&"font_size", 20)
	# без clip_text: иначе минимальная ширина метки 0 и HBox сжимает её в точку
	sub.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	sub.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var parts: PackedStringArray = []
	if str(song.get("artist", "")) != "":
		parts.append(str(song.artist))
	@warning_ignore("integer_division")
	parts.append("%d:%02d" % [dur / 60, dur % 60])
	sub.text = "  ·  ".join(parts) + "  ·  "
	sub_row.add_child(sub)
	var star_color := sub.get_theme_color(&"font_color")
	for i in stars:
		var star := TextureRect.new()
		star.texture = ICON_STAR
		star.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		star.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		star.custom_minimum_size = Vector2(18, 18)
		star.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		star.self_modulate = star_color
		star.mouse_filter = Control.MOUSE_FILTER_IGNORE
		sub_row.add_child(star)

	box.add_child(title)
	box.add_child(sub_row)
	b.add_child(box)
	# группа шлёт toggled и снятой, и новой карточке в произвольном порядке —
	# итог читаем один раз, когда она закончит
	b.toggled.connect(func(_on: bool) -> void: _sync_selection.call_deferred())
	return b


## Выбранная карточка — с оранжевой рамкой (стили pressed/hover_pressed).
func _style_selected(b: Button) -> void:
	var base := b.get_theme_stylebox(&"normal")
	var sel: StyleBox = base.duplicate() if base else StyleBoxFlat.new()
	if sel is StyleBoxFlat:
		var f := sel as StyleBoxFlat
		f.border_color = C_ACCENT
		f.set_border_width_all(3)
		f.bg_color = f.bg_color.lerp(C_ACCENT, 0.12)
	b.add_theme_stylebox_override(&"pressed", sel)
	b.add_theme_stylebox_override(&"hover_pressed", sel)


func _sync_selection() -> void:
	if not is_inside_tree() or _leaving:
		return
	var b := _song_group.get_pressed_button()
	if b == null:
		_selected = {}
		_close_cover()
		_show_board(false)
		return
	var song: Dictionary = b.get_meta(&"song", {})
	if not _selected.is_empty() and str(_selected.get("id")) == str(song.get("id")):
		return
	_selected = song
	_board_song.text = _song_label(song)
	_show_board(true)
	_load_board()


func _song_label(song: Dictionary) -> String:
	var t := str(song.get("title", "?"))
	var a := str(song.get("artist", ""))
	return t if a.is_empty() else "%s — %s" % [t, a]


func _deselect() -> void:
	var b := _song_group.get_pressed_button()
	if b:
		b.button_pressed = false   # toggled → _sync_selection сам закроет таблицу
		b.grab_focus()


# --- Таблица лидеров -----------------------------------------------------------

## Заголовок устроен как строка (те же поля и колонки), плюс справа место
## под полосу прокрутки списка — так колонки заголовка и строк совпадают.
func _build_board_header() -> void:
	var header: HBoxContainer = %BoardHeader
	for c in header.get_children():
		c.queue_free()
	_header_style = _row_style(false)
	_header_style.bg_color = Color.TRANSPARENT
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	panel.add_theme_stylebox_override(&"panel", _header_style)
	var h := HBoxContainer.new()
	h.add_theme_constant_override(&"separation", 16)
	panel.add_child(h)
	h.add_child(_cell("#", COL_RANK, HORIZONTAL_ALIGNMENT_CENTER, true))
	h.add_child(_cell("Игрок", 0.0, HORIZONTAL_ALIGNMENT_LEFT, true))
	h.add_child(_cell("Очки", COL_TOTAL, HORIZONTAL_ALIGNMENT_RIGHT, true))
	h.add_child(_cell("Ранг", COL_GRADE, HORIZONTAL_ALIGNMENT_CENTER, true))
	header.add_child(panel)
	var bar := (%BoardScroll as ScrollContainer).get_v_scroll_bar()
	bar.visibility_changed.connect(_fit_header)
	bar.resized.connect(_fit_header)
	_fit_header()


func _fit_header() -> void:
	var bar := (%BoardScroll as ScrollContainer).get_v_scroll_bar()
	_header_style.content_margin_right = ROW_PAD_R + (bar.size.x if bar.visible else 0.0)


func _row_style(me: bool) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(C_TEAL, 0.16) if me else C_ROW
	sb.set_corner_radius_all(14)
	sb.content_margin_left = ROW_PAD_L
	sb.content_margin_right = ROW_PAD_R
	sb.content_margin_top = 8
	sb.content_margin_bottom = 8
	if me:
		sb.border_color = C_TEAL
		sb.set_border_width_all(2)
	return sb


func _load_board() -> void:
	if _selected.is_empty():
		return
	_close_cover()   # сменились песня/сложность или таблица перезагружается
	_board_seq += 1
	var seq := _board_seq
	var song_id := str(_selected.get("id", ""))
	_board_message("Загружаем таблицу…", false)
	var r: Dictionary = await Api.get_leaderboard(song_id, Session.difficulty)
	if not is_inside_tree() or seq != _board_seq:
		return   # успели выбрать другую песню или сложность
	if not r.ok:
		var why: String = "песня не найдена на сервере" if r.error == "song_not_found" else str(r.error)
		_board_message("Не удалось загрузить таблицу (%s)." % why, true)
		return
	var rows: Array = r.data
	if rows.is_empty():
		_board_message("Здесь пока нет опубликованных каверов на этой сложности.\nСпойте и опубликуйте первым!", false)
		return
	_clear_board()
	if r.get("mock", false):
		var note := _cell("Сервер недоступен — таблица из мока.", 0.0, HORIZONTAL_ALIGNMENT_CENTER, true)
		_board_list.add_child(note)
	for row in rows:
		if row is Dictionary:
			_board_list.add_child(_make_row(row))


func _clear_board() -> void:
	for c in _board_list.get_children():
		_board_list.remove_child(c)
		c.queue_free()


func _board_message(text: String, can_retry: bool) -> void:
	_clear_board()
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override(&"separation", 16)
	var spacer := Control.new()
	spacer.custom_minimum_size = Vector2(0, 120)
	box.add_child(spacer)
	var l := Label.new()
	l.theme_type_variation = &"HintLabel"
	l.text = text
	l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(l)
	if can_retry:
		var b := Button.new()
		b.theme_type_variation = &"GhostButton"
		b.text = "Повторить"
		b.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
		b.pressed.connect(_load_board)
		box.add_child(b)
	_board_list.add_child(box)


## Строка таблицы: место · ник · очки · ранг. Своя строка (me) подсвечена.
## В таблице только опубликованные каверы (ADR-024): строка — кнопка, открывает окно кавера.
func _make_row(row: Dictionary) -> Control:
	var me := bool(row.get("me", false))
	var panel := Button.new()
	panel.focus_mode = Control.FOCUS_ALL
	panel.tooltip_text = "Послушать кавер"
	panel.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	var style := _row_style(me)
	var hover := style.duplicate() as StyleBoxFlat
	hover.bg_color = hover.bg_color.lerp(C_ACCENT, 0.18)
	hover.border_color = C_ACCENT
	hover.set_border_width_all(2)
	panel.add_theme_stylebox_override(&"normal", style)
	panel.add_theme_stylebox_override(&"hover", hover)
	panel.add_theme_stylebox_override(&"pressed", hover)
	panel.add_theme_stylebox_override(&"focus", hover)
	panel.pressed.connect(func() -> void: _open_cover(row, panel))

	var h := HBoxContainer.new()
	h.add_theme_constant_override(&"separation", 16)
	h.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(h)
	# кнопка не контейнер: растягиваем содержимое на всю строку и задаём высоту по нему
	h.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	h.offset_left = style.content_margin_left
	h.offset_right = -style.content_margin_right
	h.minimum_size_changed.connect(func() -> void:
		panel.custom_minimum_size.y = h.get_combined_minimum_size().y \
			+ style.content_margin_top + style.content_margin_bottom)
	var rank := int(row.get("rank", 0))
	var rank_cell := _cell(str(rank), COL_RANK, HORIZONTAL_ALIGNMENT_CENTER)
	if rank <= 3:
		rank_cell.add_theme_color_override(&"font_color", [GRADE_COLORS.S, Color(0.82, 0.84, 0.88), Color(0.86, 0.6, 0.4)][rank - 1])
	h.add_child(rank_cell)
	var player := str(row.get("player", "?"))
	# значок ноты — картинкой: символа ♪ в Nunito нет, в вебе он не рисуется
	var note := TextureRect.new()
	note.texture = ICON_NOTE
	note.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	note.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	note.custom_minimum_size = Vector2(22, 22)
	note.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	h.add_child(note)
	var name_cell := _cell(player + ("  (вы)" if me else ""), 0.0, HORIZONTAL_ALIGNMENT_LEFT)
	note.self_modulate = name_cell.get_theme_color(&"font_color")
	# ник показываем целиком: если не влез (широкие буквы), строка переносится, а не режется «…»
	name_cell.text_overrun_behavior = TextServer.OVERRUN_NO_TRIMMING
	name_cell.clip_text = false
	name_cell.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	panel.tooltip_text = "%s — послушать кавер" % player
	h.add_child(name_cell)
	h.add_child(_cell(str(int(row.get("total", 0))), COL_TOTAL, HORIZONTAL_ALIGNMENT_RIGHT))
	var grade := str(row.get("grade", "—"))
	var grade_cell := _cell(grade, COL_GRADE, HORIZONTAL_ALIGNMENT_CENTER)
	grade_cell.add_theme_color_override(&"font_color", GRADE_COLORS.get(grade, Color.WHITE))
	h.add_child(grade_cell)
	for c in h.get_children():
		(c as Control).mouse_filter = Control.MOUSE_FILTER_IGNORE
	return panel


# --- Окно кавера -------------------------------------------------------------------

func _open_cover(row: Dictionary, from: Control) -> void:
	if _leaving or _cover.is_open:
		return
	_cover_from = from
	_cover.open_row(row)


func _close_cover() -> void:
	if _cover and _cover.is_open:
		_cover.close()


func _cell(text: String, width: float, align: HorizontalAlignment, hint: bool = false) -> Label:
	var l := Label.new()
	l.text = text
	l.horizontal_alignment = align
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	l.clip_text = true
	if hint:
		l.theme_type_variation = &"HintLabel"
		l.add_theme_font_size_override(&"font_size", HEADER_FONT)
	else:
		l.add_theme_font_size_override(&"font_size", CELL_FONT)
	if width > 0.0:
		l.custom_minimum_size = Vector2(width, 0)
	else:
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


# --- Переходы -----------------------------------------------------------------

func _play(song: Dictionary) -> void:
	if _leaving or song.is_empty():
		return
	_leaving = true
	Session.song_id = str(song.get("id", ""))
	Session.song_info = song
	Session.last_result = {}
	await _fade_out()
	get_tree().change_scene_to_file(GAME_SCENE)


func _open_last_result() -> void:
	if _leaving or not Session.open_saved_result():
		return
	_leaving = true
	await _fade_out()
	get_tree().change_scene_to_file(RESULT_SCENE)


func _fade_out() -> void:
	_close_cover()
	var tw := create_tween()
	tw.tween_property(%Fade, "modulate:a", 1.0, 0.35)
	await tw.finished


func _back() -> void:
	if _leaving:
		return
	_close_cover()
	get_tree().change_scene_to_file(BOOT_SCENE)


func _unhandled_input(event: InputEvent) -> void:
	if _cover and _cover.is_open:
		return   # Esc закрывает окно кавера (ModalPanel), а не таблицу
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		if _board_open:
			_deselect()
		else:
			_back()
