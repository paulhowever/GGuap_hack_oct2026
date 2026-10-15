@tool
class_name BeatReactor
extends Node
## Переиспользуемое «ритм-поведение». Добавьте дочерним узлом к любому
## CanvasItem (Control/Node2D) и настройте в инспекторе.
## Импульс считается из фазы MenuMusic.current_beat(): 1.0 в момент доли,
## экспоненциально спадает к 0. Без музыки идёт по BPM трека (свободный ход).

enum Trigger { BEAT, MEASURE, EVERY_N_BEATS }
enum Target {
	SCALE,              ## масштаб узла (pivot — центр Control)
	BRIGHTNESS,         ## яркость modulate (умножение > 1 = «вспышка»)
	ALPHA,              ## прозрачность modulate.a
	SELF_ALPHA,         ## self_modulate.a (не влияет на детей)
	SHADER_PARAM,       ## uniform в ShaderMaterial узла
}

@export var target_node: CanvasItem            ## пусто = родитель
@export var trigger: Trigger = Trigger.BEAT
@export_range(1, 32) var every_n_beats: int = 2
@export var target: Target = Target.SCALE
@export var shader_param: StringName = &"beat_pulse"

## Сила эффекта: для SCALE — прибавка масштаба (0.06 = +6%),
## для BRIGHTNESS — прибавка яркости, для ALPHA — диапазон.
@export_range(0.0, 2.0, 0.001) var strength: float = 0.06
## Базовое значение (для ALPHA/SHADER_PARAM).
@export_range(0.0, 2.0, 0.001) var base_value: float = 0.0
## Скорость спада: больше — короче «удар».
@export_range(0.5, 30.0, 0.1) var decay: float = 7.0
## Сдвиг в долях (−0.05 = чуть раньше доли — ощущается «в такт» лучше).
@export_range(-0.5, 0.5, 0.005) var phase_shift: float = -0.02
## Сглаживание итогового значения (0 = без сглаживания).
@export_range(0.0, 0.95, 0.01) var smoothing: float = 0.0
@export var enabled: bool = true:
	set(value):
		enabled = value
		if not enabled:
			_apply(0.0)
## Работать в редакторе (для превью).
@export var preview_in_editor: bool = false

var value: float = 0.0     ## текущий импульс 0..1 (можно читать снаружи)

var _node: CanvasItem
var _base_scale: Vector2 = Vector2.ONE
var _base_modulate: Color = Color.WHITE
var _smoothed: float = 0.0


func _ready() -> void:
	_node = target_node if target_node else get_parent() as CanvasItem
	if _node == null:
		push_warning("BeatReactor: нет целевого CanvasItem")
		set_process(false)
		return
	_capture_base()
	if _node is Control:
		(_node as Control).resized.connect(_update_pivot)
		_update_pivot()


func _capture_base() -> void:
	if _node is Control:
		_base_scale = (_node as Control).scale
	elif _node is Node2D:
		_base_scale = (_node as Node2D).scale
	_base_modulate = _node.modulate


func _update_pivot() -> void:
	if target == Target.SCALE and _node is Control:
		var c := _node as Control
		c.pivot_offset = c.size * 0.5


func _process(_delta: float) -> void:
	if _node == null or not enabled:
		return
	if Engine.is_editor_hint() and not preview_in_editor:
		return
	var raw := _compute_pulse()
	_smoothed = lerpf(raw, _smoothed, smoothing) if smoothing > 0.0 else raw
	value = _smoothed
	_apply(value)


func _compute_pulse() -> float:
	var beat_pos: float
	var music := get_node_or_null(^"/root/MenuMusic")
	if music and not Engine.is_editor_hint():
		beat_pos = music.current_beat()
	else:
		beat_pos = Time.get_ticks_msec() / 1000.0 * 130.0 / 60.0
	beat_pos -= phase_shift
	var length := 1.0
	match trigger:
		Trigger.MEASURE:
			length = float(music.track.beats_per_measure) if music and music.track else 4.0
		Trigger.EVERY_N_BEATS:
			length = float(every_n_beats)
	var phase := fposmod(beat_pos, length)
	return exp(-phase * decay)


func _apply(v: float) -> void:
	if _node == null:
		return
	match target:
		Target.SCALE:
			var s := _base_scale * (1.0 + v * strength)
			if _node is Control:
				(_node as Control).scale = s
			elif _node is Node2D:
				(_node as Node2D).scale = s
		Target.BRIGHTNESS:
			var k := 1.0 + v * strength
			_node.modulate = Color(_base_modulate.r * k, _base_modulate.g * k,
				_base_modulate.b * k, _base_modulate.a)
		Target.ALPHA:
			_node.modulate.a = clampf(base_value + v * strength, 0.0, 1.0)
		Target.SELF_ALPHA:
			_node.self_modulate.a = clampf(base_value + v * strength, 0.0, 1.0)
		Target.SHADER_PARAM:
			var mat := _node.material as ShaderMaterial
			if mat:
				mat.set_shader_parameter(shader_param, base_value + v * strength)
