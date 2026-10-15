@tool
class_name OnAirSign
extends PanelContainer
## Табло «В ЭФИРЕ» как в студии: рамка + текст. Вспыхивает на каждую сильную долю,
## между ними — тлеет. Рисует собственный StyleBoxFlat (цвета из экспортов).

@export var text: String = "В ЭФИРЕ":
	set(v):
		text = v
		if _label:
			_label.text = v
@export var lit_color: Color = Color("#FF7A3D")
@export var dim_color: Color = Color("#5A3A33")
@export var bg_color: Color = Color("#1E1A24")
@export_range(0.0, 1.0) var idle_level: float = 0.35
@export_range(1.0, 20.0) var decay: float = 3.5
@export var on_air: bool = true   ## false = табло погашено (например, без музыки)

var _label: Label
var _style: StyleBoxFlat


func _ready() -> void:
	_style = StyleBoxFlat.new()
	_style.bg_color = bg_color
	_style.set_border_width_all(4)
	_style.set_corner_radius_all(12)
	_style.content_margin_left = 28
	_style.content_margin_right = 28
	_style.content_margin_top = 8
	_style.content_margin_bottom = 10
	_style.shadow_size = 0
	add_theme_stylebox_override(&"panel", _style)
	_label = Label.new()
	_label.text = text
	_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_label.theme_type_variation = &"HeadingLabel"
	_label.add_theme_font_size_override(&"font_size", 30)
	add_child(_label, false, Node.INTERNAL_MODE_FRONT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func _process(_delta: float) -> void:
	var level := 0.0
	if on_air:
		var music := get_node_or_null(^"/root/MenuMusic") if not Engine.is_editor_hint() else null
		var phase: float = music.measure_phase() if music else fposmod(Time.get_ticks_msec() / 1846.0, 1.0)
		var bpm_count: float = 4.0
		if music and music.track:
			bpm_count = music.track.beats_per_measure
		level = idle_level + (1.0 - idle_level) * exp(-phase * bpm_count * decay)
	var c := dim_color.lerp(lit_color, level)
	_style.border_color = c
	_style.shadow_color = Color(lit_color, 0.45 * level)
	_style.shadow_size = int(18.0 * level)
	_label.add_theme_color_override(&"font_color", c)
