extends CanvasLayer
## Персонаж игрока (слева) и продюсер (справа) по бокам дорожки нот.
## Живут в autoload, поэтому переживают change_scene: выезжают на игровом
## экране (во время «Загружаем песню…») и без шва остаются на экране результата.
## «Спеть ещё раз» — остаются на месте; уход к выбору песни / в меню — уезжают.
## Мышь не ловят (крутить нельзя). Пока скрыты — SubViewport не рендерится.
##
## API: enter() — выехать, leave() — уехать, dim(on) — приглушить вместе
## с затемнением сцены (%Fade) при переходах, is_shown — выехали ли.

const CHARACTER_SCENE := preload("res://ui/components/character_preview.tscn")
const PRODUCER_SCENE := preload("res://ui/components/producer_preview.tscn")

## Ширина слота персонажа, px (боковая зона у дорожки — 420 px).
const SLOT_W := 400.0
## Отступ слота от края экрана, px.
const SIDE_PAD := 10.0
## Отступы слота сверху/снизу: по высоте — область дорожки нот, над текстом песни.
const SLOT_TOP := 140.0
const SLOT_BOTTOM := 190.0
## Насколько слот уходит за край экрана в скрытом положении, px.
const HIDE_GAP := 60.0
const ENTER_SEC := 0.6
const LEAVE_SEC := 0.4
const DIM_SEC := 0.3
## Цвет приглушения (умножается на картинку) — во время затемнения сцены.
const DIM_COLOR := Color(0.45, 0.45, 0.45, 1.0)

## Выехали (или выезжают) по бокам.
var is_shown: bool = false

## 0 — за краями экрана, 1 — в слотах.
var _slide: float = 0.0:
	set(value):
		_slide = value
		_layout()

var _root: Control
var _character: CharacterPreview
var _producer: CharacterPreview
var _slide_tween: Tween
var _dim_tween: Tween


func _ready() -> void:
	# над сценой (и её %Fade), под модальными слоями с большим layer
	layer = 1
	_root = Control.new()
	_root.name = "Root"
	_root.set_anchors_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_root)
	_character = _make(CHARACTER_SCENE, "Character", 0.0)
	_producer = _make(PRODUCER_SCENE, "Producer", 1.0)
	_layout()


func _make(scene: PackedScene, node_name: String, anchor_x: float) -> CharacterPreview:
	var p := scene.instantiate() as CharacterPreview
	p.name = node_name
	p.interactive = false
	p.anchor_left = anchor_x
	p.anchor_right = anchor_x
	p.anchor_top = 0.0
	p.anchor_bottom = 1.0
	p.offset_top = SLOT_TOP
	p.offset_bottom = -SLOT_BOTTOM
	_root.add_child(p)
	p.set_active(false)
	return p


## Выехать по бокам. Повторный вызов, когда уже выехали, ничего не делает.
func enter() -> void:
	if is_shown:
		return
	is_shown = true
	_character.set_active(true)
	_producer.set_active(true)
	_tween_slide(1.0, ENTER_SEC, Tween.EASE_OUT)


## Уехать за края экрана; после этого превью выключаются (не рендерятся).
func leave() -> void:
	if not is_shown:
		return
	is_shown = false
	var tw := _tween_slide(0.0, LEAVE_SEC, Tween.EASE_IN)
	tw.tween_callback(func() -> void:
		if not is_shown:
			_character.set_active(false)
			_producer.set_active(false))


## Приглушить (on) / вернуть яркость — синхронно с затемнением сцены.
func dim(on: bool) -> void:
	if _dim_tween and _dim_tween.is_valid():
		_dim_tween.kill()
	_dim_tween = create_tween()
	_dim_tween.tween_property(_root, "modulate", DIM_COLOR if on else Color.WHITE, DIM_SEC)


func _tween_slide(to: float, sec: float, ease_type: Tween.EaseType) -> Tween:
	if _slide_tween and _slide_tween.is_valid():
		_slide_tween.kill()
	_slide_tween = create_tween()
	_slide_tween.tween_property(self, ^"_slide", to, sec) \
		.set_trans(Tween.TRANS_BACK).set_ease(ease_type)
	return _slide_tween


## Слоты привязаны якорями к краям экрана, поэтому раскладка не зависит
## от ширины окна (stretch aspect = expand).
func _layout() -> void:
	if _character == null:
		return
	var left := lerpf(-SLOT_W - HIDE_GAP, SIDE_PAD, _slide)
	_character.offset_left = left
	_character.offset_right = left + SLOT_W
	var right := lerpf(HIDE_GAP, -SIDE_PAD - SLOT_W, _slide)
	_producer.offset_left = right
	_producer.offset_right = right + SLOT_W
