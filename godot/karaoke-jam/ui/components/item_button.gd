class_name ItemButton
extends RhythmMenuButton
## Кнопка предмета гардероба. Внутри — свой SubViewport (own_world_3d) с моделью
## предмета. Пока кнопка в фокусе (наведение мыши тоже даёт фокус) модель
## вращается, после — плавно останавливается.
## Предмет задаётся через item_def (каталог res://items/catalog.tres) — кнопки
## гардероб создаёт сам. Модель автоматически вписывается в кадр.
## Надетый предмет подсвечивается (equipped).

## Цвет рамки и подписи у надетого предмета.
const EQUIPPED_COLOR := Color(1.0, 0.478, 0.239, 1.0)
const EQUIPPED_BORDER := 4
## Сколько кадров рендерить после показа/изменения размера/остановки вращения.
const REDRAW_FRAMES := 2
## Размер, к которому приводится наибольшая сторона модели в превью.
const FIT_SIZE := 1.0

@export var item_def: ItemDef:
	set(v):
		item_def = v
		if is_node_ready():
			_apply_def()
@export var spin_speed_deg: float = 120.0

## Предмет надет на персонажа — кнопка подсвечена.
var equipped: bool = false:
	set(v):
		if v == equipped:
			return
		equipped = v
		if is_node_ready():
			_apply_equipped()

var item_id: StringName:
	get:
		return item_def.id if item_def else &""
var slot: StringName:
	get:
		return item_def.slot if item_def else &""

var _spin: float = 0.0
## Рендер по требованию: 3D-вид кнопки перерисовывается только пока модель
## крутится и ещё REDRAW_FRAMES кадров после показа/ресайза/остановки.
## В остальное время SubViewport выключен и показывает последний кадр.
var _redraw_frames: int = REDRAW_FRAMES
var _model: Node3D

@onready var _pivot: Node3D = %Pivot
@onready var _item: MeshInstance3D = %ItemMesh
@onready var _label: Label = %NameLabel
@onready var _view: SubViewportContainer = $Margin/VBox/View
@onready var _viewport: SubViewport = $Margin/VBox/View/SubViewport


func _ready() -> void:
	super._ready()
	_item.queue_free()  # заглушка из сцены не нужна: модель берётся из item_def
	_apply_def()
	_apply_equipped()
	visibility_changed.connect(request_redraw)
	_view.resized.connect(request_redraw)
	_viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED


## Перерисовать 3D-вид в ближайших кадрах (после смены модели, цвета и т. п.).
func request_redraw() -> void:
	_redraw_frames = REDRAW_FRAMES


func _apply_def() -> void:
	if _model:
		_model.queue_free()
		_model = null
	var title := item_def.display_name if item_def else ""
	_label.text = title
	tooltip_text = title
	if item_def == null or item_def.scene == null:
		return
	var inst := item_def.scene.instantiate() as Node3D
	if inst == null:
		return
	# Fit — центрирует и масштабирует модель так, чтобы она влезла в кадр
	_model = Node3D.new()
	_model.name = "Fit"
	_model.rotation_degrees = item_def.preview_rotation_deg
	_pivot.add_child(_model)
	var box := _local_aabb(inst, Transform3D.IDENTITY)
	var longest := box.get_longest_axis_size()
	var k := FIT_SIZE / longest if longest > 0.0001 else 1.0
	inst.scale = Vector3.ONE * k
	inst.position = -box.get_center() * k
	_model.add_child(inst)
	request_redraw()


func _apply_equipped() -> void:
	for state: StringName in [&"normal", &"hover", &"focus", &"pressed"]:
		remove_theme_stylebox_override(state)
	_label.remove_theme_color_override(&"font_color")
	if equipped:
		for state: StringName in [&"normal", &"hover", &"focus", &"pressed"]:
			var base := get_theme_stylebox(state) as StyleBoxFlat
			if base == null:
				continue
			var sb := base.duplicate() as StyleBoxFlat
			sb.border_color = EQUIPPED_COLOR
			sb.set_border_width_all(EQUIPPED_BORDER)
			add_theme_stylebox_override(state, sb)
		_label.add_theme_color_override(&"font_color", EQUIPPED_COLOR)
	request_redraw()


## AABB всех мешей поддерева в системе координат корня (узел ещё не в дереве,
## поэтому трансформы перемножаются вручную).
func _local_aabb(node: Node, xf: Transform3D) -> AABB:
	var box := AABB()
	var has := false
	if node is Node3D:
		xf = xf * (node as Node3D).transform
	var mi := node as MeshInstance3D
	if mi and mi.mesh:
		box = xf * mi.mesh.get_aabb()
		has = true
	for c in node.get_children():
		var cb := _local_aabb(c, xf)
		if cb.size == Vector3.ZERO and cb.position == Vector3.ZERO:
			continue
		box = box.merge(cb) if has else cb
		has = true
	return box


func _process(delta: float) -> void:
	super._process(delta)
	var target := 1.0 if has_focus() else 0.0
	_spin = lerpf(_spin, target, 1.0 - exp(-delta * 8.0))
	var spinning := _spin > 0.001
	if spinning:
		_pivot.rotate_y(deg_to_rad(spin_speed_deg) * _spin * delta)
		_redraw_frames = REDRAW_FRAMES  # после остановки дорисуем финальную позу
	_update_render_mode()


## SubViewportContainer при каждом показе сам включает UPDATE_ALWAYS,
## поэтому режим выставляется здесь каждый кадр, а не один раз в .tscn.
func _update_render_mode() -> void:
	var mode := SubViewport.UPDATE_DISABLED
	if is_visible_in_tree() and _redraw_frames > 0:
		mode = SubViewport.UPDATE_ALWAYS
		_redraw_frames -= 1
	if _viewport.render_target_update_mode != mode:
		_viewport.render_target_update_mode = mode
