extends Node
## Аудио-сервис — фасад над VoiceBridge (ADR-001: весь звук игры живёт в JS).
## Микрофон, минус, питч и запись дубля — в web/voice.js; здесь только:
## - статус микрофона для UI (MicState) по событиям моста и уровню из poll();
## - калибровка задержки: Godot лишь анимирует щелчки по таймеру (та же сетка, что в
##   web/lib/calibration.js, режим «headphones»: 2 вводных + 8 измеряемых щелчков,
##   шаг 0.8 с, первый через 0.6 с), а итог (lag_ms, hits) возвращает JS. Успех — hits ≥ 5.
## Нативный микрофон Godot (AudioStreamMicrophone) больше не используется.

signal mic_state_changed(state: MicState)
signal level_changed(rms: float, peak: float)
## index — 1..CAL_TOTAL по всем щелчкам; первые CAL_LEAD_IN — вводные (не измеряются).
signal calibration_click(index: int, total: int)
signal calibration_finished(success: bool, lag_ms: int, hits: int)

enum MicState { OFF, STARTING, ACTIVE, SILENT, ERROR }

const _Bridge = preload("res://autoload/voice_bridge.gd")
const CAL_CLICKS := _Bridge.CAL_CLICKS
const CAL_LEAD_IN := _Bridge.CAL_LEAD_IN
const CAL_TOTAL := CAL_LEAD_IN + CAL_CLICKS
const CAL_LEAD_SEC := _Bridge.CAL_LEAD
const CAL_GAP_SEC := _Bridge.CAL_GAP
const CAL_MIN_HITS := _Bridge.CAL_MIN_HITS
## Уровень (rms), выше которого считаем, что в микрофоне есть звук.

const ACTIVE_RMS := 0.0005
const SILENT_AFTER_SEC := 3.0

const MIC_ERRORS: Array[String] = ["insecure_context", "mic_denied", "mic_not_found", "audio_locked", "worklet_failed"]

var mic_state: MicState = MicState.OFF:
	set(value):
		if value == mic_state:
			return
		mic_state = value
		mic_state_changed.emit(mic_state)

var rms_level: float = 0.0
var peak_level: float = 0.0
var is_calibrating: bool = false
## Код последней ошибки микрофона (для подсказок в UI), "" — нет.
var mic_error: String = ""

var _silent_time: float = 0.0
var _cal_elapsed: float = 0.0
var _cal_index: int = 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	VoiceBridge.unlocked.connect(_on_unlocked)
	VoiceBridge.bridge_error.connect(_on_bridge_error)
	VoiceBridge.calibrated.connect(_on_calibrated)
	VoiceBridge.polled.connect(_on_polled)
	if VoiceBridge.is_unlocked:
		_on_unlocked(VoiceBridge.unlock_info)
	elif VoiceBridge.is_web_bridge():
		mic_state = MicState.STARTING


# --- Микрофон (только статус) ---------------------------------------------

## Микрофон открывает оверлей shell.html (voice.unlock()). Отсюда — только повтор
## после ошибки; в вебе вызывать из обработчика клика.
func enable_mic() -> void:
	if is_mic_on():
		return
	mic_state = MicState.STARTING
	VoiceBridge.unlock()


func is_mic_on() -> bool:
	return mic_state in [MicState.STARTING, MicState.ACTIVE, MicState.SILENT]


func is_bt_suspect() -> bool:
	return bool(VoiceBridge.unlock_info.get("bt_suspect", false))


func _on_unlocked(_info: Dictionary) -> void:
	mic_error = ""
	_silent_time = 0.0
	mic_state = MicState.ACTIVE


func _on_bridge_error(code: String, _msg: String) -> void:
	if code in MIC_ERRORS:
		mic_error = code
		mic_state = MicState.ERROR


func _on_polled() -> void:
	var delta := get_process_delta_time()
	rms_level = VoiceBridge.level
	peak_level = maxf(rms_level, peak_level - delta * 1.5)
	level_changed.emit(rms_level, peak_level)
	if not VoiceBridge.is_unlocked or mic_state == MicState.ERROR:
		return
	# В заглушке/моке уровень есть только во время песни — не пугаем «тишиной».
	if VoiceBridge.is_mock():
		mic_state = MicState.ACTIVE
		return
	if rms_level > ACTIVE_RMS:
		_silent_time = 0.0
		mic_state = MicState.ACTIVE
	else:
		_silent_time += delta
		if _silent_time > SILENT_AFTER_SEC:
			mic_state = MicState.SILENT


# --- Калибровка -------------------------------------------------------------

func start_calibration() -> void:
	if is_calibrating or VoiceBridge.is_calibrating:
		return   # JS игнорирует повторный calibrate(), а таймер Godot шёл бы второй раз
	is_calibrating = true
	_cal_elapsed = 0.0
	_cal_index = 0
	MenuMusic.duck(true)
	VoiceBridge.calibrate()


## Отменить нельзя на стороне JS — просто перестаём анимировать и игнорируем итог.
func cancel_calibration() -> void:
	if not is_calibrating:
		return
	is_calibrating = false
	MenuMusic.duck(false)


func _process(delta: float) -> void:
	if not is_calibrating:
		return
	_cal_elapsed += delta
	while _cal_index < CAL_TOTAL and _cal_elapsed >= CAL_LEAD_SEC + _cal_index * CAL_GAP_SEC:
		_cal_index += 1
		calibration_click.emit(_cal_index, CAL_TOTAL)


func _on_calibrated(lag_ms: int, hits: int) -> void:
	if not is_calibrating:
		return
	is_calibrating = false
	MenuMusic.duck(false)
	# дорисовать оставшиеся щелчки, если JS ответил раньше таймера
	while _cal_index < CAL_TOTAL:
		_cal_index += 1
		calibration_click.emit(_cal_index, CAL_TOTAL)
	var ok := hits >= CAL_MIN_HITS
	if ok:
		Session.set_calibrated_lag(lag_ms)
	calibration_finished.emit(ok, Session.lag_ms, hits)


func get_calibration_bpm() -> float:
	return 60.0 / CAL_GAP_SEC
