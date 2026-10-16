class_name CustomizePanel
extends ModalPanel
## Гардероб: персонаж «перелетает» из логотипа стартового экрана в крупное превью
## по центру, справа выезжает карточка с предметами, слева — карточка «Профиль»
## (ник и «О себе», единственное место, где они меняются). При закрытии — всё обратно,
## персонаж по пути возвращается к исходному углу и бесшовно подменяется
## превью логотипа.
## Анимация построена на offset_transform_* (Godot 4.6+): это визуальное смещение
## поверх раскладки, контейнеры его не перезаписывают.
## Клик по фону окно не закрывает; закрытие — «Назад» или Esc.

## Начало закрытия (для синхронной анимации экрана под окном).
signal closing
## Нажата кнопка предмета (наряд уже обновлён через Session.equip_item:
## ненадетый предмет надевается, надетый — снимается).
signal item_pressed(item_id: StringName, slot: StringName)

const ITEM_BUTTON_SCENE := preload("res://ui/components/item_button.tscn")

const OPEN_TIME := 0.55
const CLOSE_TIME := 0.45
const CARD_SHIFT := 720.0
const ITEM_SHIFT := 140.0
## Сколько отрисованных кадров держать панель видимой при прогреве шейдеров.
const WARM_UP_FRAMES := 3

## Во сколько раз уменьшать разрешение крупного превью во время перелёта
## (1 — не уменьшать). В покое превью всегда в полном разрешении.
@export_range(1, 4) var flight_shrink: int = 2

## Превью, из которого вылетает персонаж (задаёт экран-владелец).
var source_preview: CharacterPreview

var _tween: Tween
var _warming: bool = false
## Прогресс перелёта: 0 — крупное превью поверх source_preview, 1 — на своём месте.
## Смещение пересчитывается по текущим прямоугольникам на каждом шаге твина,
## поэтому не зависит от того, успела ли раскладка контейнеров к началу анимации.
var _fly: float = 1.0:
	set(v):
		_fly = v
		_apply_fly()

@onready var _preview: CharacterPreview = %Preview
@onready var _grid: GridContainer = %ItemGrid
@onready var _back: Button = %BackButton
@onready var _profile: Control = %ProfileCard
@onready var _nick: LineEdit = %NickEdit
@onready var _bio: TextEdit = %BioEdit
@onready var _bio_counter: Label = %BioCounter


func _ready() -> void:
	super._ready()
	_preview.set_active(false)
	_back.pressed.connect(close)
	_build_items()
	Session.outfit_changed.connect(func(_s: StringName, _i: StringName) -> void: _refresh_equipped())
	_refresh_equipped()
	for c: Control in [_preview, _card, _profile] + _items():
		c.offset_transform_enabled = true
	_nick.max_length = Session.NICKNAME_MAX
	_nick.text_submitted.connect(func(_t: String) -> void:
		_apply_nick()
		_nick.release_focus())
	_nick.focus_exited.connect(_apply_nick)
	_bio.text_changed.connect(_on_bio_changed)
	_bio.focus_exited.connect(_apply_bio)
	_load_profile()


func open() -> void:
	if is_open or _warming:
		return
	is_open = true
	_kill_tween()
	var from_closed := not visible
	visible = true
	if from_closed:
		# первая раскладка контейнеров — только после показа
		modulate.a = 0.0
		await get_tree().process_frame
		if not is_open:
			return
		modulate.a = 1.0
		_dim.modulate.a = 0.0
		_card.modulate.a = 0.0
		_card.offset_transform_position = Vector2(CARD_SHIFT, 0.0)
		_profile.modulate.a = 0.0
		_profile.offset_transform_position = Vector2(-CARD_SHIFT, 0.0)
		for b: ItemButton in _items():
			b.offset_transform_position = Vector2(ITEM_SHIFT, 0.0)
		_fly = 0.0
	_load_profile()
	_preview.cancel_return()
	# сначала включаем, потом копируем кадр анимации (см. copy_state_from)
	_preview.set_active(true)
	if source_preview and source_preview.modulate.a > 0.0:
		_preview.copy_state_from(source_preview)
		source_preview.set_active(false)
	_set_flight_resolution(true)

	_tween = create_tween().set_parallel()
	_tween.tween_property(_dim, ^"modulate:a", 1.0, 0.3)
	_tween.tween_property(self, ^"_fly", 1.0, OPEN_TIME) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
	_tween.finished.connect(_set_flight_resolution.bind(false))
	_tween.tween_property(_card, ^"modulate:a", 1.0, 0.25).set_delay(0.15)
	_tween.tween_property(_card, ^"offset_transform_position", Vector2.ZERO, 0.5) \
		.set_delay(0.15).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_tween.tween_property(_profile, ^"modulate:a", 1.0, 0.25).set_delay(0.15)
	_tween.tween_property(_profile, ^"offset_transform_position", Vector2.ZERO, 0.5) \
		.set_delay(0.15).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	var i := 0
	for b: ItemButton in _items():
		_tween.tween_property(b, ^"offset_transform_position", Vector2.ZERO, 0.45) \
			.set_delay(0.25 + 0.035 * i).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
		i += 1
	_on_opened()
	if initial_focus:
		initial_focus.grab_focus.call_deferred()
	opened.emit()


func close() -> void:
	%NickLabel.visible = true
	if not is_open:
		return
	is_open = false
	_kill_tween()
	_apply_nick()
	_apply_bio()
	_on_closing()
	closing.emit()
	var focus := get_viewport().gui_get_focus_owner()
	if focus and is_ancestor_of(focus):
		focus.release_focus()

	_preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var yaw_tween := _preview.return_to_rest()
	_set_flight_resolution(true)
	_tween = create_tween().set_parallel()
	_tween.tween_property(_dim, ^"modulate:a", 0.0, CLOSE_TIME)
	_tween.tween_property(_card, ^"modulate:a", 0.0, 0.25)
	_tween.tween_property(_card, ^"offset_transform_position", Vector2(CARD_SHIFT, 0.0), 0.3) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	_tween.tween_property(_profile, ^"modulate:a", 0.0, 0.25)
	_tween.tween_property(_profile, ^"offset_transform_position", Vector2(-CARD_SHIFT, 0.0), 0.3) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN)
	_tween.tween_property(self, ^"_fly", 0.0, CLOSE_TIME) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_IN_OUT)
	var tw := _tween
	await tw.finished
	if yaw_tween and yaw_tween.is_running():
		await yaw_tween.finished
	if is_open or tw != _tween:
		return  # окно успели открыть заново
	if source_preview:
		# сначала включаем, потом копируем кадр анимации (см. copy_state_from)
		source_preview.set_active(true)
		source_preview.copy_state_from(_preview)
		# SubViewport логотипа был выключен с момента открытия и хранит старый кадр;
		# новый он нарисует только на ближайшей отрисовке. Держим его прозрачным,
		# пока кадр не готов, — иначе на кадр мелькает поза до открытия гардероба.
		source_preview.modulate.a = 0.0
		await RenderingServer.frame_post_draw
		if is_open or tw != _tween:
			source_preview.set_active(false)   # окно успели открыть заново
			return
		source_preview.modulate.a = 1.0
	_preview.set_active(false)
	_set_flight_resolution(false)
	visible = false
	closed.emit()


## Прогрев шейдеров: панель на несколько кадров становится видимой, но
## прозрачной, — все её 3D-виды рисуются, и WebGL компилирует шейдеры заранее,
## а не в момент первого открытия. Вызывать, пока экран закрыт заставкой.
func warm_up() -> void:
	if is_open or visible:
		return
	_warming = true
	modulate.a = 0.0
	visible = true
	_preview.set_active(true)
	for i in WARM_UP_FRAMES:
		await RenderingServer.frame_post_draw
	_preview.set_active(false)
	visible = false
	modulate.a = 1.0
	_warming = false


## Клик по пустому месту окно не закрывает, но снимает фокус с полей профиля
## (так ник/«О себе» сохраняются, и Esc снова закрывает окно).
func _on_dim_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		var focus := get_viewport().gui_get_focus_owner()
		if focus == _nick or focus == _bio:
			focus.release_focus()


# --- Профиль: ник и «О себе» ------------------------------------------------------

func _load_profile() -> void:
	_nick.text = Session.nickname
	_bio.text = Session.bio
	_update_bio_counter()


## Ник из поля в Session (пустой → «Гость»); поле показывает итоговое значение.
func _apply_nick() -> void:
	if _nick.text.strip_edges() != Session.nickname:
		Session.nickname = _nick.text
		Session.save_settings()
	if _nick.text != Session.nickname:
		_nick.text = Session.nickname


func _apply_bio() -> void:
	if _bio.text.strip_edges() != Session.bio:
		Session.bio = _bio.text
		Session.save_settings()


## У TextEdit нет max_length: лишнее обрезается сразу, курсор остаётся в конце вставки.
func _on_bio_changed() -> void:
	if _bio.text.length() > Session.BIO_MAX:
		var line := _bio.get_caret_line()
		var col := _bio.get_caret_column()
		_bio.text = _bio.text.left(Session.BIO_MAX)
		line = mini(line, _bio.get_line_count() - 1)
		_bio.set_caret_line(line)
		_bio.set_caret_column(mini(col, _bio.get_line(line).length()))
	_update_bio_counter()


func _update_bio_counter() -> void:
	var n := _bio.text.length()
	_bio_counter.text = "%d / %d" % [n, Session.BIO_MAX]
	_bio_counter.modulate = Color(1.0, 0.6, 0.4) if n >= Session.BIO_MAX else Color.WHITE


## Esc в поле профиля сначала снимает фокус (и сохраняет), а не закрывает окно.
func _unhandled_input(event: InputEvent) -> void:
	if is_open and event.is_action_pressed(&"ui_cancel"):
		var focus := get_viewport().gui_get_focus_owner()
		if focus == _nick or focus == _bio:
			focus.release_focus()
			get_viewport().set_input_as_handled()
			return
	super._unhandled_input(event)


## Кнопки предметов создаются по каталогу (res://items/catalog.tres).
func _build_items() -> void:
	for c in _grid.get_children():
		c.queue_free()
		_grid.remove_child(c)
	for def: ItemDef in ItemCatalog.get_default().items:
		if def == null or def.scene == null:
			continue
		var b: ItemButton = ITEM_BUTTON_SCENE.instantiate()
		b.name = String(def.id).to_pascal_case()
		b.item_def = def
		_grid.add_child(b)
		b.pressed.connect(_on_item_button.bind(b))


## Клик по ненадетому предмету надевает его (вытесняя предмет того же слота),
## по надетому — снимает.
func _on_item_button(b: ItemButton) -> void:
	var worn := Session.get_equipped(b.slot) == b.item_id
	Session.equip_item(b.slot, &"" if worn else b.item_id)
	item_pressed.emit(b.item_id, b.slot)


## Подсветка кнопок по текущему наряду.
func _refresh_equipped() -> void:
	for b: ItemButton in _items():
		b.equipped = Session.get_equipped(b.slot) == b.item_id


func _items() -> Array[ItemButton]:
	var out: Array[ItemButton] = []
	for c in _grid.get_children():
		if c is ItemButton:
			out.append(c)
	return out


## Ставит крупное превью между источником (_fly = 0) и своим местом (_fly = 1).
func _apply_fly() -> void:
	if not is_node_ready():
		return
	var t := _source_offset()
	_preview.offset_transform_scale = (t.scale as Vector2).lerp(Vector2.ONE, _fly)
	_preview.offset_transform_position = (t.position as Vector2).lerp(Vector2.ZERO, _fly)


## Во время перелёта крупное превью рендерится в пониженном разрешении.
func _set_flight_resolution(flying: bool) -> void:
	_preview.stretch_shrink = maxi(flight_shrink, 1) if flying else 1


## Прямоугольник крупного превью в раскладке, без учёта offset_transform.
func _preview_rest_rect() -> Rect2:
	var parent := _preview.get_parent_control()
	return parent.get_global_transform() * Rect2(_preview.position, _preview.size)


## offset_transform, при котором _preview совпадает с source_preview на экране.
func _source_offset() -> Dictionary:
	var dst := _preview_rest_rect()
	if source_preview == null or dst.size.x <= 0.0:
		return {scale = Vector2.ONE, position = Vector2.ZERO}
	var src := source_preview.get_global_rect()
	var s := src.size.x / dst.size.x
	return {scale = Vector2(s, s), position = src.get_center() - dst.get_center()}


func _kill_tween() -> void:
	if _tween and _tween.is_valid():
		_tween.kill()
	_tween = null
