@tool
class_name ScoreRing
extends Control
## Круглый индикатор процента (как accuracy в osu!): дуга от 12 часов по часовой.
## Цвет вдоль дуги — градиент от красного (0 %) до голубо-золотого (100 %),
## т. е. чем выше процент, тем «теплее-холоднее-золотее» конец дуги.
## Содержимое (процент, подпись) кладётся дочерними узлами поверх.

const C_TRACK := Color(0.953, 0.902, 0.827, 0.08)

@export_range(0.0, 100.0) var value: float = 0.0:
	set(v):
		value = clampf(v, 0.0, 100.0)
		queue_redraw()
@export var thickness: float = 22.0:
	set(v):
		thickness = v
		queue_redraw()
@export var gradient: Gradient:
	set(v):
		gradient = v
		queue_redraw()


func _init() -> void:
	if gradient == null:
		gradient = make_default_gradient()


## Красный → оранжевый → жёлтый → голубой проекта → золото.
static func make_default_gradient() -> Gradient:
	var g := Gradient.new()
	g.offsets = PackedFloat32Array([0.0, 0.4, 0.65, 0.85, 1.0])
	g.colors = PackedColorArray([
		Color(1.0, 0.365, 0.365),   # #FF5D5D
		Color(1.0, 0.549, 0.102),   # #FF8C1A
		Color(1.0, 0.8, 0.25),      # #FFCC40
		Color(0.373, 0.827, 0.737), # #5FD3BC
		Color(1.0, 0.82, 0.35),     # золото
	])
	return g


func _draw() -> void:
	var c := size * 0.5
	var r := minf(size.x, size.y) * 0.5 - thickness * 0.5
	if r <= 1.0:
		return
	var frac := value / 100.0

	draw_arc(c, r, 0.0, TAU, 128, C_TRACK, thickness, true)
	if frac <= 0.0:
		return

	var n := maxi(2, ceili(180.0 * frac))
	var pts := PackedVector2Array()
	var cols := PackedColorArray()
	for k in n + 1:
		var p := frac * float(k) / float(n)
		var ang := -PI * 0.5 + TAU * p
		pts.append(c + Vector2(cos(ang), sin(ang)) * r)
		cols.append(gradient.sample(p))

	draw_polyline_colors(pts, cols, thickness, true)
	# скруглённые концы дуги
	draw_circle(pts[0], thickness * 0.5, cols[0], true, -1.0, true)
	draw_circle(pts[pts.size() - 1], thickness * 0.5, cols[cols.size() - 1], true, -1.0, true)
