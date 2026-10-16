class_name ProducerPreview
extends CharacterPreview
## Продюсер справа от дорожки нот (autoload Performers). Наряды на него не
## надеваются. Анимация зависит от экрана (set_mood), все переходы — с блендом:
##  • SONG при появлении — вступление intro_animation, затем бленд в song_animation;
##  • SONG, когда уже на экране («Ещё раз» с результата) — бленд в song_animation;
##  • RESULT — бленд в result_animation.

enum Mood { SONG, RESULT }

## Вступление при появлении в начале песни (играет один раз).
@export var intro_animation: StringName = &"Armature|mixamo_com|Layer0_002"
## Пока идёт песня (по кругу).
@export var song_animation: StringName = &"MUSIC_IDLE"
## На экране результата (по кругу).
@export var result_animation: StringName = &"mixamo_com"
## Длительность бленда между анимациями, с.
@export_range(0.0, 2.0, 0.05, "suffix:s") var blend_time: float = 0.5
## Кость-корень (бёдра): по её треку считается, насколько вступление уводит
## персонажа с места.
@export var hips_bone: StringName = &"mixamorig_Hips"

var mood: Mood = Mood.SONG

## Только что появился (был выключен) — следующий SONG начнётся со вступления.
var _fresh: bool = true
## Насколько вступление сдвигает бёдра по полу (в осях модели) — во время
## вступления модель смещена на минус это, чтобы оно заканчивалось в центре.
var _intro_shift: Vector3 = Vector3.ZERO
var _shift_tween: Tween


func _ready() -> void:
	super()
	# бленд и для play() без явного времени, и для очереди (intro → song)
	_anim.playback_default_blend_time = blend_time
	_intro_shift = _hips_travel(intro_animation)
	_anim.animation_changed.connect(_on_animation_changed)


func set_active(on: bool) -> void:
	if on and not _active:
		_fresh = true
	super(on)


## Переключает анимацию под экран. Повторный вызов с тем же настроением
## не перезапускает анимацию.
func set_mood(value: Mood) -> void:
	var fresh := _fresh
	_fresh = false
	if value == mood and not fresh and _anim.is_playing():
		return
	mood = value
	_anim.clear_queue()
	match value:
		Mood.SONG:
			if fresh and _anim.has_animation(intro_animation):
				# вступление с начала и без бленда: персонаж только что выехал
				_kill_shift()
				_set_shift(-_intro_shift)
				_anim.play(intro_animation, 0.0)
				_anim.seek(0.0, true)
				_anim.queue(song_animation)
			else:
				_play(song_animation)
		Mood.RESULT:
			_play(result_animation)


func _play(anim_name: StringName) -> void:
	if not _anim.has_animation(anim_name):
		push_warning("ProducerPreview: нет анимации «%s»" % anim_name)
		return
	if _anim.current_animation == anim_name:
		return
	var from := _anim.current_animation
	_anim.play(anim_name, blend_time)
	_on_animation_changed(from, anim_name)


## Уход со вступления (по очереди или прерыванием): смещение модели убирается
## линейно за время бленда — вместе с весом бленда, поэтому бёдра стоят на месте.
func _on_animation_changed(old_name: StringName, _new_name: StringName) -> void:
	if old_name != intro_animation or _model.position.is_zero_approx():
		return
	if _shift_tween and _shift_tween.is_valid():
		_shift_tween.kill()
	_shift_tween = create_tween()
	_shift_tween.tween_property(_model, ^"position", Vector3.ZERO, blend_time)


## Смещение в осях модели (с учётом поворота yaw) → позиция модели.
func _set_shift(local_shift: Vector3) -> void:
	_model.position = _model.basis * local_shift


func _kill_shift() -> void:
	if _shift_tween and _shift_tween.is_valid():
		_shift_tween.kill()
	_shift_tween = null
	_model.position = Vector3.ZERO


## Насколько анимация сдвигает кость hips_bone по полу от первого до последнего
## кадра, в осях модели (Y обнулён). Нет анимации или трека — ноль.
func _hips_travel(anim_name: StringName) -> Vector3:
	if not _anim.has_animation(anim_name):
		return Vector3.ZERO
	var anim := _anim.get_animation(anim_name)
	var skeletons := _model.find_children("*", "Skeleton3D", true, false)
	if skeletons.is_empty():
		return Vector3.ZERO
	var sk := skeletons[0] as Skeleton3D
	var track_path := NodePath("%s:%s" % [_anim.get_node(_anim.root_node).get_path_to(sk), hips_bone])
	var track := anim.find_track(track_path, Animation.TYPE_POSITION_3D)
	if track < 0:
		return Vector3.ZERO
	# позиция корневой кости — в осях скелета; переводим в оси модели
	var to_model := _model.global_transform.affine_inverse() * sk.global_transform
	var a := to_model * anim.position_track_interpolate(track, 0.0)
	var b := to_model * anim.position_track_interpolate(track, anim.length)
	var d := b - a
	d.y = 0.0
	return d
