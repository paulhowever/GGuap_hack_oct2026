@tool
class_name EqBars
extends Control
## Столбики эквалайзера «студийного пульта». Берут уровни из SpectrumAnalyzer
## на шине Music; если его нет / музыка молчит — анимируются по фазе бита.
## Рисуются через _draw (без текстур), цвета — из экспортов (палитра темы).

@export_range(4, 64) var bar_count: int = 14
@export_range(0.0, 1.0) var gap_ratio: float = 0.35
@export var color_low: Color = Color("#5FD3BC")
@export var color_high: Color = Color("#FF7A3D")
@export var color_off: Color = Color(0.953, 0.902, 0.827, 0.06)
@export_range(4, 40) var segments: int = 18
@export var mirror: bool = false         ## заполнять сверху вниз
@export var horizontal: bool = false     ## столбики растут вбок (для боковых панелей)
@export var flip_horizontal: bool = false  ## растут влево (для правой панели)
@export_range(20.0, 400.0) var freq_min: float = 60.0
@export_range(1000.0, 16000.0) var freq_max: float = 9000.0
@export_range(0.0, 3.0) var gain: float = 1.0
@export var bus: StringName = &"Music"

var _levels: PackedFloat32Array = PackedFloat32Array()
var _peaks: PackedFloat32Array = PackedFloat32Array()
var _spectrum: AudioEffectSpectrumAnalyzerInstance


func _ready() -> void:
	_levels.resize(bar_count)
	_peaks.resize(bar_count)
	if not Engine.is_editor_hint():
		var idx := AudioServer.get_bus_index(bus)
		if idx >= 0:
			for i in AudioServer.get_bus_effect_count(idx):
				if AudioServer.get_bus_effect(idx, i) is AudioEffectSpectrumAnalyzer:
					_spectrum = AudioServer.get_bus_effect_instance(idx, i)
					break


func _process(delta: float) -> void:
	if _levels.size() != bar_count:
		_levels.resize(bar_count)
		_peaks.resize(bar_count)
	var music := get_node_or_null(^"/root/MenuMusic")
	var beat_pulse: float = music.pulse(5.0) if music else exp(-fposmod(Time.get_ticks_msec() / 461.5, 1.0) * 5.0)
	var t := Time.get_ticks_msec() / 1000.0
	for i in bar_count:
		var target := 0.0
		if _spectrum and music and music.is_running:
			var f0 := freq_min * pow(freq_max / freq_min, float(i) / bar_count)
			var f1 := freq_min * pow(freq_max / freq_min, float(i + 1) / bar_count)
			var mag := _spectrum.get_magnitude_for_frequency_range(f0, f1).length()
			var db := linear_to_db(maxf(mag, 0.00001))
			target = clampf((db + 62.0) / 52.0, 0.0, 1.0) * gain
		else:
			# «холостой» режим: псевдослучайные столбики, подпрыгивают на долю
			var n := 0.5 + 0.5 * sin(t * (1.3 + i * 0.37) + i * 2.1)
			target = 0.15 + 0.35 * n + 0.45 * beat_pulse * (0.5 + 0.5 * sin(i * 1.7))
		var cur := _levels[i]
		cur = lerpf(cur, target, 1.0 - exp(-delta * (22.0 if target > cur else 7.0)))
		_levels[i] = cur
		_peaks[i] = maxf(cur, _peaks[i] - delta * 0.6)
	queue_redraw()


func _draw() -> void:
	var length_axis := size.x if horizontal else size.y
	var cross_axis := size.y if horizontal else size.x
	var slot := cross_axis / bar_count
	var bar_w := slot * (1.0 - gap_ratio)
	var seg_len := length_axis / segments
	var seg_fill := seg_len * 0.7
	for i in bar_count:
		var lvl := _levels[i] if i < _levels.size() else 0.0
		var lit := int(round(lvl * segments))
		var peak_seg := int(round((_peaks[i] if i < _peaks.size() else 0.0) * segments))
		for s in segments:
			var k := float(s) / (segments - 1)
			var col: Color
			if s < lit:
				col = color_low.lerp(color_high, k * k)
			elif s == peak_seg and peak_seg > 0:
				col = color_high
				col.a = 0.7
			else:
				col = color_off
			var along := s * seg_len
			if not mirror:
				along = length_axis - along - seg_fill
			var across := i * slot + (slot - bar_w) * 0.5
			var r: Rect2
			if horizontal:
				var x := along
				if flip_horizontal:
					x = length_axis - along - seg_fill
				r = Rect2(x, across, seg_fill, bar_w)
			else:
				r = Rect2(across, along, bar_w, seg_fill)
			draw_rect(r, col)
