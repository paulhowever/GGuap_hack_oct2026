extends Node
## Глобальное состояние игрока: ник, задержка, первый запуск, настройки.
## Всё хранится в user://settings.cfg (в вебе — IndexedDB браузера).

signal nickname_changed(nickname: String)
signal lag_changed(lag_ms: int)
signal headphones_changed(confirmed: bool)
signal music_volume_changed(value: float)

const SAVE_PATH := "user://settings.cfg"
const DEFAULT_NICKNAME := "Гость"
const LAG_MIN_MS := 0
const LAG_MAX_MS := 500

var nickname: String = DEFAULT_NICKNAME:
	set(value):
		value = value.strip_edges().left(24)
		if value.is_empty():
			value = DEFAULT_NICKNAME
		if value == nickname:
			return
		nickname = value
		nickname_changed.emit(nickname)

## Суммарная задержка «звук услышан → голос в микрофоне», мс.
var lag_ms: int = 120:
	set(value):
		value = clampi(value, LAG_MIN_MS, LAG_MAX_MS)
		if value == lag_ms:
			return
		lag_ms = value
		lag_changed.emit(lag_ms)

var is_calibrated: bool = false
var first_run_done: bool = false

## Игрок подтвердил, что поёт в проводных наушниках (автоопределение невозможно).
var headphones_confirmed: bool = false:
	set(value):
		if value == headphones_confirmed:
			return
		headphones_confirmed = value
		headphones_changed.emit(headphones_confirmed)

## Громкость музыки 0..1 (линейная), применяется к шине Music.
var music_volume: float = 0.8:
	set(value):
		music_volume = clampf(value, 0.0, 1.0)
		_apply_music_volume()
		music_volume_changed.emit(music_volume)


func _ready() -> void:
	load_settings()


func is_first_run() -> bool:
	return not first_run_done


func mark_first_run_done() -> void:
	first_run_done = true
	save_settings()


func set_calibrated_lag(value_ms: int) -> void:
	lag_ms = value_ms
	is_calibrated = true
	save_settings()


func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SAVE_PATH) == OK:
		nickname = cfg.get_value("player", "nickname", DEFAULT_NICKNAME)
		lag_ms = cfg.get_value("audio", "lag_ms", lag_ms)
		is_calibrated = cfg.get_value("audio", "is_calibrated", false)
		headphones_confirmed = cfg.get_value("audio", "headphones_confirmed", false)
		music_volume = cfg.get_value("audio", "music_volume", music_volume)
		first_run_done = cfg.get_value("app", "first_run_done", false)
	_apply_music_volume()


func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("player", "nickname", nickname)
	cfg.set_value("audio", "lag_ms", lag_ms)
	cfg.set_value("audio", "is_calibrated", is_calibrated)
	cfg.set_value("audio", "headphones_confirmed", headphones_confirmed)
	cfg.set_value("audio", "music_volume", music_volume)
	cfg.set_value("app", "first_run_done", first_run_done)
	var err := cfg.save(SAVE_PATH)
	if err != OK:
		push_warning("Session: не удалось сохранить настройки (%s)" % error_string(err))


## Сброс к «первому запуску» — удобно для отладки.
func reset_settings() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SAVE_PATH))
	first_run_done = false
	is_calibrated = false


func _apply_music_volume() -> void:
	var idx := AudioServer.get_bus_index(&"Music")
	if idx >= 0:
		AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(music_volume, 0.0001)))
