class_name ModalPanel
extends Control
## База для модальных окон: затемнение + карточка по центру, анимация
## появления/скрытия, Esc закрывает (если allow_close). Наследники
## заполняют %Card своим содержимым в своей сцене.

signal opened
signal closed

@export var allow_close: bool = true
@export var dim_color: Color = Color(0.07, 0.06, 0.09, 0.72)
## Контрол, получающий фокус при открытии (для клавиатуры).
@export var initial_focus: Control

var is_open: bool = false

@onready var _dim: ColorRect = %Dim
@onready var _card: Control = %Card


func _ready() -> void:
	_dim.color = dim_color
	visible = false
	mouse_filter = Control.MOUSE_FILTER_STOP
	_dim.gui_input.connect(_on_dim_input)


func open() -> void:
	if is_open:
		return
	is_open = true
	visible = true
	_card.pivot_offset = _card.size * 0.5
	_dim.modulate.a = 0.0
	_card.modulate.a = 0.0
	_card.scale = Vector2(0.92, 0.92)
	var tw := create_tween().set_parallel()
	tw.tween_property(_dim, "modulate:a", 1.0, 0.2)
	tw.tween_property(_card, "modulate:a", 1.0, 0.2)
	tw.tween_property(_card, "scale", Vector2.ONE, 0.35) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_on_opened()
	if initial_focus:
		initial_focus.grab_focus.call_deferred()
	opened.emit()


func close() -> void:
	if not is_open:
		return
	is_open = false
	_on_closing()
	var tw := create_tween().set_parallel()
	tw.tween_property(_dim, "modulate:a", 0.0, 0.15)
	tw.tween_property(_card, "modulate:a", 0.0, 0.15)
	tw.tween_property(_card, "scale", Vector2(0.95, 0.95), 0.15)
	await tw.finished
	if not is_open:
		visible = false
	closed.emit()


## Переопределяются наследниками.
func _on_opened() -> void:
	pass


func _on_closing() -> void:
	pass


func _unhandled_input(event: InputEvent) -> void:
	if is_open and allow_close and event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		close()


func _on_dim_input(event: InputEvent) -> void:
	if allow_close and event is InputEventMouseButton and event.pressed:
		close()
