extends Node
## Обёртка над аддоном Conductor для фоновой музыки меню.
## - задаёт трек/BPM/фазу из TrackInfo;
## - зацикливает фрагмент и сбрасывает счётчики Conductor, иначе после
##   перемотки назад сигналы beat/measure перестают приходить;
## - даёт удобные хелперы фазы для UI (beat_phase, pulse).
##
## UI подписывается на Conductor.beat / Conductor.measure напрямую
## или использует сигналы ниже (они дублируют Conductor, но переживают смену трека).

signal beat(beat_index: int)
signal measure(measure_index: int)
signal started
signal stopped

const DEFAULT_TRACK := "res://audio/tracks/menu_track.tres"
const FADE_SEC := 0.6

var track: TrackInfo
var is_running: bool = false

var _conductor: Node
var _fade_tween: Tween


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_conductor = get_node_or_null(^"/root/Conductor")
	if _conductor == null:
		push_error("MenuMusic: autoload Conductor не найден — включите аддон conductor")
		return
	_conductor.bus = &"Music"
	_conductor.beat.connect(func(i: int) -> void: beat.emit(i))
	_conductor.measure.connect(func(i: int) -> void: measure.emit(i))
	if ResourceLoader.exists(DEFAULT_TRACK):
		track = load(DEFAULT_TRACK)


## Запускает музыку меню (вызывать после пользовательского жеста — правило браузеров).
func start(from_track: TrackInfo = null) -> void:
	if _conductor == null:
		return
	if is_running and _conductor.playing and (from_track == null or from_track == track):
		return   # уже играет — при возврате в меню не перезапускаем
	if from_track:
		track = from_track
	if track == null or track.stream == null:
		push_warning("MenuMusic: трек не задан")
		return
	# set_song игнорирует тот же stream, поэтому параметры выставляем сами.
	_conductor.stop()
	_conductor.stream = null
	_conductor.set_song(track.stream, track.bpm, track.beats_per_measure, track.conductor_offset())
	_play_from(track.resolved_start_sec())
	is_running = true
	_fade_to(0.0, FADE_SEC)
	started.emit()


func stop(fade: bool = true) -> void:
	if _conductor == null or not is_running:
		return
	is_running = false
	if fade:
		await _fade_to(-60.0, FADE_SEC)
	if not is_running:
		_conductor.stop()
	stopped.emit()


## Приглушить (например, на время калибровки).
func duck(enabled: bool, db: float = -60.0) -> void:
	if _conductor:
		_fade_to(db if enabled else 0.0, 0.3)


## Текущая доля (дробная). Без музыки — свободно идущее время по BPM.
func current_beat() -> float:
	if _conductor and is_running and _conductor.playing:
		return _conductor.current_beat
	var bpm := track.bpm if track else 120.0
	return Time.get_ticks_msec() / 1000.0 * bpm / 60.0


## 0..1 внутри текущей доли.
func beat_phase() -> float:
	return fposmod(current_beat(), 1.0)


## 0..1 внутри текущего такта.
func measure_phase() -> float:
	var bpm_count := track.beats_per_measure if track else 4
	return fposmod(current_beat(), float(bpm_count)) / bpm_count


## Импульс 1→0 с экспоненциальным спадом после каждой доли (для пульсаций).
func pulse(sharpness: float = 6.0) -> float:
	return exp(-beat_phase() * sharpness)


func _process(_delta: float) -> void:
	if not is_running or _conductor == null or track == null:
		return
	var loop_end := track.resolved_loop_end_sec()
	var pos: float = _conductor.get_playback_position()
	var ended: bool = not _conductor.playing
	if ended or (loop_end > 0.0 and pos >= loop_end - 0.02):
		_play_from(track.resolved_loop_start_sec())


func _play_from(sec: float) -> void:
	# Сброс внутренних счётчиков Conductor, чтобы сигналы снова шли с новой позиции.
	sec = maxf(sec, 0.0)
	var start_beat := (sec + track.conductor_offset()) / track.sec_per_beat()
	_conductor.last_reported_beat = floori(start_beat) - 1
	_conductor.current_measure = floori(start_beat / track.beats_per_measure)
	_conductor.last_reported_measure = _conductor.current_measure - 1
	_conductor.last_reported_update = start_beat
	_conductor.is_playing_offset = false
	_conductor.play(sec)


func _fade_to(db: float, duration: float) -> Signal:
	if _fade_tween and _fade_tween.is_valid():
		_fade_tween.kill()
	_fade_tween = create_tween()
	_fade_tween.tween_property(_conductor, "volume_db", db, duration)
	return _fade_tween.finished
