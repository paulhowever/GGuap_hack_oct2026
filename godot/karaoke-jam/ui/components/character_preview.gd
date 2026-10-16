class_name CharacterPreview
extends SubViewportContainer
## 3D-персонаж в своём SubViewport (own_world_3d — таких превью на экране может
## быть несколько). Перетаскивание мышью крутит его вокруг вертикальной оси без
## ограничений; короткое нажатие без перетаскивания — «клик» (сигнал clicked).
## С auto_return после отпускания персонаж плавно возвращается к rest_yaw
## кратчайшим путём: накрученные 1000° превращаются в поворот на −80°.

signal clicked

## Исходный угол поворота модели вокруг Y.
@export_range(-180.0, 180.0, 0.5, "radians_as_degrees") var rest_yaw: float = deg_to_rad(15.0)
## Возвращаться к rest_yaw после отпускания мыши.
@export var auto_return: bool = true
## Сколько градусов поворота даёт один пиксель перетаскивания.
@export var drag_sensitivity_deg: float = 0.5
## Смещение (px), после которого нажатие считается перетаскиванием, а не кликом.
@export var click_threshold: float = 6.0
## Длительность возврата при отклонении на 180° (меньшие углы — быстрее).
@export var return_time: float = 0.6
## Можно крутить мышью и кликать. false — превью только для показа:
## мышь проходит насквозь (персонажи по бокам дорожки нот, autoload Performers).
@export var interactive: bool = true:
	set(value):
		interactive = value
		if is_node_ready():
			_apply_mouse()

## Текущий угол модели (радианы, без нормализации — может быть сколько угодно оборотов).
var yaw: float = 0.0:
	set(value):
		yaw = value
		if _model:
			_model.rotation.y = value

var _active: bool = true
var _pressed: bool = false
var _dragging: bool = false
var _press_pos: Vector2
var _return_tween: Tween

@onready var _viewport: SubViewport = $SubViewport
@onready var _model: Node3D = %GV_Anim_Pack_1
@onready var _anim: AnimationPlayer = $SubViewport/GV_Anim_Pack_1/AnimationPlayer


func _ready() -> void:
	yaw = rest_yaw
	_apply_mouse()


func _gui_input(event: InputEvent) -> void:
	if not interactive:
		return
	var mb := event as InputEventMouseButton
	if mb and mb.button_index == MOUSE_BUTTON_LEFT:
		if mb.pressed:
			_pressed = true
			_dragging = false
			_press_pos = mb.position
			_kill_return()
		elif _pressed:
			_pressed = false
			if _dragging:
				if auto_return:
					return_to_rest()
			else:
				clicked.emit()
			_dragging = false
		accept_event()
		return
	var mm := event as InputEventMouseMotion
	if mm and _pressed:
		if not _dragging:
			if mm.position.distance_to(_press_pos) > click_threshold:
				_dragging = true
				# учитываем уже пройденный путь, чтобы не было рывка на пороге
				yaw += deg_to_rad((mm.position.x - _press_pos.x) * drag_sensitivity_deg)
		else:
			yaw += deg_to_rad(mm.relative.x * drag_sensitivity_deg)
		accept_event()


func _notification(what: int) -> void:
	# SubViewportContainer при показе сам ставит SubViewport режим UPDATE_ALWAYS
	# (код движка срабатывает раньше скрипта) — выключенное превью гасим обратно
	if what == NOTIFICATION_VISIBILITY_CHANGED and not _active and _viewport:
		_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	if what == NOTIFICATION_VISIBILITY_CHANGED and not is_visible_in_tree() and _pressed:
		_pressed = false
		_dragging = false
		if auto_return:
			return_to_rest()


## Плавный возврат к rest_yaw кратчайшим путём (не больше 180°).
## Возвращает твин (или null, если уже на месте) — его можно дождаться.
func return_to_rest() -> Tween:
	_kill_return()
	var diff := wrapf(yaw - rest_yaw, -PI, PI)
	# тот же визуальный угол, но без лишних оборотов
	yaw = rest_yaw + diff
	if absf(diff) < 0.001:
		yaw = rest_yaw
		return null
	var t := lerpf(0.25, return_time, absf(diff) / PI)
	_return_tween = create_tween()
	_return_tween.tween_property(self, ^"yaw", rest_yaw, t) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	return _return_tween


## Перенимает угол и кадр анимации у другого превью (для бесшовной подмены).
func copy_state_from(other: CharacterPreview) -> void:
	if other == null or other == self:
		return
	_kill_return()
	yaw = other.yaw
	var anim_name := other._anim.current_animation
	if anim_name == &"":
		return
	# seek применяется только у активного AnimationPlayer: у выключенного
	# поза не обновится — включаем на время перемотки
	var was_active := _anim.active
	_anim.active = true
	_anim.speed_scale = other._anim.speed_scale
	_anim.play(anim_name)
	_anim.seek(other._anim.current_animation_position, true)
	_anim.active = was_active


## Выключенное превью невидимо, не рендерится, не анимируется и не ловит мышь.
func set_active(on: bool) -> void:
	_active = on
	modulate.a = 1.0 if on else 0.0
	_apply_mouse()
	_viewport.render_target_update_mode = SubViewport.UPDATE_WHEN_PARENT_VISIBLE if on \
		else SubViewport.UPDATE_DISABLED
	_anim.active = on
	if not on:
		_pressed = false
		_dragging = false


## Мышь ловит только включённое интерактивное превью (interactive).
func _apply_mouse() -> void:
	var on := _active and interactive
	mouse_filter = MOUSE_FILTER_STOP if on else MOUSE_FILTER_IGNORE
	mouse_default_cursor_shape = CURSOR_POINTING_HAND if on else CURSOR_ARROW
	if not on:
		_pressed = false
		_dragging = false


## Прерывает возврат к rest_yaw (угол остаётся текущим).
func cancel_return() -> void:
	_kill_return()


func _kill_return() -> void:
	if _return_tween and _return_tween.is_valid():
		_return_tween.kill()
	_return_tween = null
