class_name SingerPreview
extends CharacterPreview
## Персонаж игрока слева от дорожки нот (autoload Performers).
## Анимация зависит от экрана (set_mood), переходы — с блендом, как у продюсера:
##  • SONG — idle_animation (по умолчанию IDOL на скорости 0.5);
##  • RESULT — result_animation (joke, по кругу). Если персонаж только что
##    выехал («Мой последний результат»), сначала коротко играет idle_animation.
## Во время песни (SONG) реагирует на громкость микрофона: растягивается вверх
## (до max_stretch) и наклоняется в сторону дорожки нот (до max_lean).
## Чтобы растянутый/наклонённый персонаж не обрезался, превью может быть больше
## «кадра» (frame_margin_top / frame_margin_side, px): камера пересчитывается так,
## что в покое персонаж стоит там же и того же размера, что и без запаса.

enum Mood { SONG, RESULT }

## Пока идёт песня (по кругу).
@export var idle_animation: StringName = &"Armature|IDOL"
## Скорость idle_animation.
@export_range(0.05, 4.0, 0.05) var idle_speed: float = 0.5
## На экране результата (по кругу).
@export var result_animation: StringName = &"Armature|joke"
## Скорость result_animation.
@export_range(0.05, 4.0, 0.05) var result_speed: float = 1.0
## Сколько играет idle_animation перед result_animation, если персонаж
## только что появился на экране результата, с.
@export_range(0.0, 5.0, 0.05, "suffix:s") var result_intro_time: float = 0.8
## Длительность бленда между анимациями, с.
@export_range(0.0, 2.0, 0.05, "suffix:s") var blend_time: float = 0.5

@export_group("Микрофон")
## Растяжение вверх при максимальной громкости (1 — без растяжения).
@export_range(1.0, 2.0, 0.01) var max_stretch: float = 1.25
## Наклон в сторону дорожки нот при максимальной громкости.
@export_range(0.0, 90.0, 0.5, "radians_as_degrees") var max_lean: float = deg_to_rad(30.0)
## Наклоняться вправо по экрану (дорожка нот справа от персонажа).
@export var lean_right: bool = true
## Шарнир наклона по горизонтали (м, от центра модели в сторону наклона) —
## передняя кромка ступней: при наклоне всё остальное только поднимается
## и не уходит под низ кадра.
@export var lean_pivot: float = 0.15
## Усиление уровня микрофона: level = clamp(sqrt(rms) * level_gain, 0, 1)
## (та же шкала, что у полоски чипа микрофона).
@export var level_gain: float = 2.2
## Время нарастания реакции (громче), с.
@export_range(0.01, 1.0, 0.01, "suffix:s") var attack_time: float = 0.08
## Время возврата (тише / конец песни), с.
@export_range(0.01, 2.0, 0.01, "suffix:s") var release_time: float = 0.3

@export_group("Запас кадра")
## Запас сверху над «кадром», px (для растяжения вверх).
@export var frame_margin_top: float = 0.0:
	set(value):
		frame_margin_top = value
		_fit_camera()
## Запас сбоку (в сторону наклона), px.
@export var frame_margin_side: float = 0.0:
	set(value):
		frame_margin_side = value
		_fit_camera()

var mood: Mood = Mood.SONG

## Только что появился (был выключен) — RESULT начнётся с короткого idle.
var _fresh: bool = true
## Целевой уровень микрофона 0..1 (из AudioService) и сглаженный.
var _target_level: float = 0.0
var _level: float = 0.0
## Узел-шарнир у ног модели: на нём растяжение и наклон, на модели — yaw.
var _lean: Node3D
var _camera: Camera3D
var _cam_size: float = 1.0
var _cam_pos: Vector3
var _mood_tween: Tween


func _ready() -> void:
	super()
	_camera = _viewport.get_node(^"Camera3D") as Camera3D
	_cam_size = _camera.size
	_cam_pos = _camera.position
	# шарнир в начале координат (у ног); модель — внутрь, её transform не меняется
	_lean = Node3D.new()
	_lean.name = "Lean"
	_viewport.add_child(_lean)
	_model.reparent(_lean, false)
	resized.connect(_fit_camera)
	_fit_camera()
	AudioService.level_changed.connect(_on_level_changed)
	set_process(_active)


func set_active(on: bool) -> void:
	if on and not _active:
		_fresh = true
	super(on)
	set_process(on)
	if not on:
		_kill_mood_tween()
		_target_level = 0.0
		_level = 0.0
		_apply_level()


## Переключает анимацию под экран. Повторный вызов с тем же настроением
## не перезапускает анимацию.
func set_mood(value: Mood) -> void:
	var fresh := _fresh
	_fresh = false
	if value == mood and not fresh and _anim.is_playing():
		return
	mood = value
	_kill_mood_tween()
	if value != Mood.SONG:
		_target_level = 0.0
	match value:
		Mood.SONG:
			_play(idle_animation, idle_speed)
		Mood.RESULT:
			if fresh and result_intro_time > 0.0:
				_play(idle_animation, idle_speed)
				_mood_tween = create_tween()
				_mood_tween.tween_interval(result_intro_time)
				_mood_tween.tween_callback(_play.bind(result_animation, result_speed))
			else:
				_play(result_animation, result_speed)


func _play(anim_name: StringName, speed: float) -> void:
	if not _anim.has_animation(anim_name):
		push_warning("SingerPreview: нет анимации «%s»" % anim_name)
		return
	if _anim.current_animation == anim_name:
		return
	_anim.play(anim_name, blend_time, speed)


func _on_level_changed(rms: float, _peak: float) -> void:
	if mood != Mood.SONG or not _active:
		_target_level = 0.0
		return
	_target_level = clampf(sqrt(maxf(rms, 0.0)) * level_gain, 0.0, 1.0)


func _process(delta: float) -> void:
	if _level == _target_level:
		return
	# экспоненциальное сглаживание: быстро вверх, плавно вниз
	var tau := attack_time if _target_level > _level else release_time
	_level = lerpf(_level, _target_level, 1.0 - exp(-delta / tau))
	if absf(_level - _target_level) < 0.001:
		_level = _target_level
	_apply_level()


## Сглаженный уровень → растяжение по вертикали и наклон (вокруг ног).
func _apply_level() -> void:
	if _lean == null:
		return
	var stretch_y := lerpf(1.0, max_stretch, _level)
	# поворот вокруг оси взгляда камеры (Z): отрицательный угол — макушка вправо
	var dir := 1.0 if lean_right else -1.0
	var angle := -max_lean * _level * dir
	# растяжение от пола, поворот вокруг шарнира у передней кромки ступней
	var pivot := Vector3(lean_pivot * dir, 0.0, 0.0)
	var b := Basis(Vector3.BACK, angle) * Basis.from_scale(Vector3(1.0, stretch_y, 1.0))
	_lean.transform = Transform3D(b, pivot - b * pivot)


## Камера с запасом кадра: масштаб (px на метр) и положение персонажа на экране
## те же, что у превью без запаса размером (size − запас).
func _fit_camera() -> void:
	if _camera == null or size.y <= frame_margin_top + 1.0:
		return
	var base_h := size.y - frame_margin_top
	var ppu := base_h / _cam_size   # keep_aspect = KEEP_HEIGHT
	_camera.size = size.y / ppu
	var side := frame_margin_side if lean_right else -frame_margin_side
	_camera.position = _cam_pos + Vector3(side * 0.5 / ppu, frame_margin_top * 0.5 / ppu, 0.0)


func _kill_mood_tween() -> void:
	if _mood_tween and _mood_tween.is_valid():
		_mood_tween.kill()
	_mood_tween = null
