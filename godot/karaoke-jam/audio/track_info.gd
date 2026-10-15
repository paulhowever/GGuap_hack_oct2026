@tool
class_name TrackInfo
extends Resource
## Описание музыкального трека для Conductor. Редактируется в инспекторе.

@export var title: String = ""
@export var stream: AudioStream
@export_range(40.0, 260.0, 0.01) var bpm: float = 130.0
@export_range(1, 16) var beats_per_measure: int = 4

## Время (сек) любой заведомо сильной доли (начала такта).
## Из него вычисляется фаза сетки долей. Подстраивайте на слух.
@export_range(0.0, 600.0, 0.001, "suffix:s") var beat_anchor_sec: float = 44.0

## Тонкая подстройка фазы в мс (+ — сетка позже, − — раньше).
@export_range(-500.0, 500.0, 1.0, "suffix:ms") var nudge_ms: float = 0.0

## С какого места играть трек в меню (сек). -1 = с якоря.
@export_range(-1.0, 600.0, 0.01, "suffix:s") var start_sec: float = -1.0

## Куда возвращаться при зацикливании (сек). -1 = на start.
@export_range(-1.0, 600.0, 0.01, "suffix:s") var loop_start_sec: float = -1.0

## Где обрывать цикл (сек). 0 = конец трека.
@export_range(0.0, 600.0, 0.01, "suffix:s") var loop_end_sec: float = 0.0


func sec_per_beat() -> float:
	return 60.0 / bpm


func sec_per_measure() -> float:
	return sec_per_beat() * beats_per_measure


## Смещение для Conductor.first_beat_offset: после него начало такта
## выпадает ровно на beat_anchor_sec (номер доли кратен beats_per_measure).
func conductor_offset() -> float:
	var anchor := beat_anchor_sec + nudge_ms / 1000.0
	return -fposmod(anchor, sec_per_measure())


func resolved_start_sec() -> float:
	return beat_anchor_sec if start_sec < 0.0 else start_sec


func resolved_loop_start_sec() -> float:
	return resolved_start_sec() if loop_start_sec < 0.0 else loop_start_sec


func resolved_loop_end_sec() -> float:
	if loop_end_sec > 0.0:
		return loop_end_sec
	return stream.get_length() if stream else 0.0
