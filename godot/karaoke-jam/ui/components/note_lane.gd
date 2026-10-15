class_name NoteLane
extends Control
## Дорожка нот: время течёт справа налево, playhead — вертикальная линия.
## По вертикали — высота (MIDI) в диапазоне песни ± запас.
## Голос игрока — след из кадров VoiceBridge.frames; октава приводится к ближайшей
## к нотам (в караоке поют в удобной октаве, оценка тоже не штрафует октаву).
## Оценённые ноты перекрашиваются по hit (0..1).

const PX_PER_SEC := 260.0
const PLAYHEAD_FRAC := 0.28
const MIDI_PAD := 4.0
const TRAIL_SEC := 3.0
const NOTE_H := 22.0

const C_LANE := Color(0.165, 0.141, 0.2, 0.85)
const C_GRID := Color(1, 1, 1, 0.05)
const C_PLAYHEAD := Color(0.373, 0.827, 0.737)
const C_NOTE := Color(0.953, 0.902, 0.827, 0.85)
const C_GOLDEN := Color(1.0, 0.8, 0.25)
const C_RAP := Color(0.6, 0.55, 0.95)
const C_TRAIL := Color(1.0, 0.478, 0.239)
const C_HIT := Color(0.373, 0.827, 0.537)
const C_MISS := Color(1.0, 0.365, 0.365)

## [{i, line, type, midi, t, end, hit (-1 = ещё не оценена)}]
var notes: Array = []
var t_now: float = 0.0
var _midi_lo: float = 55.0
var _midi_hi: float = 72.0
var _trail: Array = []   # [{t, midi}] ; midi < 0 — разрыв (тишина)
var _by_index: Dictionary = {}


func set_reference(ref: Dictionary) -> void:
	notes.clear()
	_by_index.clear()
	_trail.clear()
	var lo := 1000.0
	var hi := -1000.0
	for line in ref.get("lines", []):
		for n in line.get("notes", []):
			var item := {"i": int(n.i), "line": int(line.i), "type": str(n.get("type", "normal")),
				"midi": float(n.midi), "t": float(n.t), "end": float(n.t) + float(n.d), "hit": -1.0}
			notes.append(item)
			_by_index[item.i] = item
			if item.type != "free":
				lo = minf(lo, item.midi)
				hi = maxf(hi, item.midi)
	if lo <= hi:
		_midi_lo = lo - MIDI_PAD
		_midi_hi = hi + MIDI_PAD
	queue_redraw()


func judge(i: int, hit: float) -> void:
	if _by_index.has(i):
		_by_index[i].hit = hit
		queue_redraw()


## Координата Y центра ноты — пригодится для всплывающих оценок.
func note_position(i: int) -> Vector2:
	if not _by_index.has(i):
		return Vector2(_playhead_x(), size.y * 0.5)
	var n: Dictionary = _by_index[i]
	return Vector2(_playhead_x(), _y(n.midi))


func push_frames(frames: Array, now: float) -> void:
	t_now = now
	for f in frames:
		var hz := float(f.get("hz", 0.0))
		var conf := float(f.get("conf", 0.0))
		var t := float(f.get("t", now))
		if hz <= 0.0 or conf < 0.5:
			_trail.append({"t": t, "midi": -1.0})
			continue
		_trail.append({"t": t, "midi": _fold_octave(69.0 + 12.0 * log(hz / 440.0) / log(2.0), t)})
	while not _trail.is_empty() and float(_trail[0].t) < now - TRAIL_SEC:
		_trail.pop_front()
	queue_redraw()


func _fold_octave(m: float, t: float) -> float:
	var target := (_midi_lo + _midi_hi) * 0.5
	for n: Dictionary in notes:
		if t >= n.t - 0.3 and t < n.end + 0.3 and n.type != "free":
			target = n.midi
			break
	return m + 12.0 * roundf((target - m) / 12.0)


func _playhead_x() -> float:
	return size.x * PLAYHEAD_FRAC


func _x(t: float) -> float:
	return _playhead_x() + (t - t_now) * PX_PER_SEC


func _y(midi: float) -> float:
	var k := inverse_lerp(_midi_lo, _midi_hi, midi)
	return lerpf(size.y - NOTE_H, NOTE_H, k)


func _draw() -> void:
	draw_rect(Rect2(Vector2.ZERO, size), C_LANE)
	var m := ceilf(_midi_lo)
	while m <= _midi_hi:
		draw_line(Vector2(0, _y(m)), Vector2(size.x, _y(m)), C_GRID, 1.0)
		m += 1.0
	# ноты
	for n: Dictionary in notes:
		var x0 := _x(n.t)
		var x1 := _x(n.end)
		if x1 < 0.0 or x0 > size.x:
			continue
		var col := C_NOTE
		match n.type:
			"golden", "rap_golden":
				col = C_GOLDEN
			"rap":
				col = C_RAP
			"free":
				col = Color(C_NOTE, 0.25)
		if n.hit >= 0.0:
			col = C_MISS.lerp(C_HIT, clampf(n.hit, 0.0, 1.0))
		var r := Rect2(x0, _y(n.midi) - NOTE_H * 0.5, maxf(x1 - x0, 4.0), NOTE_H)
		draw_style_box(_pill(col), r)
	# след голоса
	var pts := PackedVector2Array()
	for p: Dictionary in _trail:
		if p.midi < 0.0:
			_flush_trail(pts)
			pts = PackedVector2Array()
			continue
		pts.append(Vector2(_x(p.t), _y(p.midi)))
	_flush_trail(pts)
	# playhead
	var px := _playhead_x()
	draw_line(Vector2(px, 0), Vector2(px, size.y), C_PLAYHEAD, 3.0)


func _flush_trail(pts: PackedVector2Array) -> void:
	if pts.size() >= 2:
		draw_polyline(pts, C_TRAIL, 5.0, true)
	elif pts.size() == 1:
		draw_circle(pts[0], 3.0, C_TRAIL)


var _pill_cache: Dictionary = {}

func _pill(col: Color) -> StyleBoxFlat:
	var key := col.to_html()
	if not _pill_cache.has(key):
		var sb := StyleBoxFlat.new()
		sb.bg_color = col
		sb.set_corner_radius_all(int(NOTE_H * 0.5))
		sb.anti_aliasing = true
		_pill_cache[key] = sb
	return _pill_cache[key]


func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		queue_redraw()
