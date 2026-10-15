class_name RhythmMenuButton
extends Button
## Кнопка меню в стиле osu!: пружинит при наведении/фокусе, «подпрыгивает» на долю,
## пока выбрана. Стиль задаётся вариацией темы (PrimaryButton/GhostButton).

@export_range(0.0, 0.3, 0.005) var hover_scale: float = 0.06
@export_range(0.0, 0.2, 0.005) var beat_scale: float = 0.035
@export var hover_shift: float = 18.0   ## сдвиг вправо при наведении (px)
@export var beat_when_idle: bool = false

var _hovered: bool = false
var _hover_amount: float = 0.0
var _press_amount: float = 0.0


func _ready() -> void:
	mouse_entered.connect(_set_hover.bind(true))
	mouse_exited.connect(_set_hover.bind(false))
	focus_entered.connect(_set_hover.bind(true))
	focus_exited.connect(_set_hover.bind(false))
	button_down.connect(func() -> void: _press_amount = 1.0)
	resized.connect(func() -> void: pivot_offset = size * 0.5)
	pivot_offset = size * 0.5


func _set_hover(on: bool) -> void:
	_hovered = on or has_focus() or is_hovered()
	if on and not has_focus() and focus_mode != FOCUS_NONE:
		grab_focus()


func _process(delta: float) -> void:
	_hover_amount = lerpf(_hover_amount, 1.0 if _hovered else 0.0, 1.0 - exp(-delta * 14.0))
	_press_amount = move_toward(_press_amount, 0.0, delta * 6.0)
	var beat := 0.0
	if _hovered or beat_when_idle:
		var music := get_node_or_null(^"/root/MenuMusic")
		if music:
			beat = music.pulse(7.0)
	var s := 1.0 + _hover_amount * hover_scale + beat * beat_scale - _press_amount * 0.05
	scale = Vector2(s, s)


## Слайд-вход слева с задержкой (вызывает меню).
func play_intro(delay: float) -> void:
	var final_x := position.x
	modulate.a = 0.0
	position.x = final_x - 120.0
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "modulate:a", 1.0, 0.35).set_delay(delay)
	tw.tween_property(self, "position:x", final_x, 0.6).set_delay(delay) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
