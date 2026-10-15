extends Node
## Аудио-сервис на чистом Godot (без JS):
## - микрофон: AudioStreamMicrophone → шина "Mic" (AudioEffectCapture, фейдер -80 дБ,
##   чтобы не было самопрослушки);
## - индикатор уровня (RMS / peak);
## - калибровка задержки: щелчки по сетке BPM, игрок хлопает/говорит «та»,
##   ловим онсеты в микрофоне, медиана разниц = lag_ms.
## Запись дорожки голоса — заглушка (start_recording/stop_recording) под будущий геймплей.

signal mic_state_changed(state: MicState)
signal level_changed(rms: float, peak: float)
signal calibration_click(index: int, total: int)
signal calibration_hit(index: int, lag_ms: float)
signal calibration_finished(success: bool, lag_ms: int, hits: int)

enum MicState { OFF, STARTING, ACTIVE, SILENT, ERROR }

const MIC_BUS := &"Mic"
const SFX_BUS := &"Sfx"

## Калибровка (свой BPM, не зависит от трека меню)
const CAL_BPM := 100.0
const CAL_CLICKS := 10
const CAL_WARMUP_CLICKS := 2          # первые щелчки — «вход в ритм», не учитываются
const CAL_MIN_VALID := 4
const CAL_MAX_LAG_MS := 450.0
const ONSET_MIN_PEAK := 0.08          # абсолютный порог пика
const ONSET_RATIO := 4.0              # во сколько раз громче фонового уровня
const ONSET_REFRACTORY_SEC := 0.18

var mic_state: MicState = MicState.OFF:
	set(value):
		if value == mic_state:
			return
		mic_state = value
		mic_state_changed.emit(mic_state)

var rms_level: float = 0.0
var peak_level: float = 0.0
var is_calibrating: bool = false
var is_recording: bool = false

var _mic_player: AudioStreamPlayer
var _capture: AudioEffectCapture
var _click_player: AudioStreamPlayer
var _mix_rate: float = 44100.0
var _frames_total: int = 0            # сколько кадров микрофона прочитано
var _mic_t0_usec: int = 0             # время, соответствующее кадру 0
var _noise_floor: float = 0.01
var _silent_time: float = 0.0
var _last_onset_sec: float = -10.0
var _onsets_sec: Array[float] = []

var _cal_click_times: Array[float] = []
var _cal_timer: float = 0.0
var _cal_index: int = 0
var _recorded: PackedVector2Array = PackedVector2Array()


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	_mix_rate = AudioServer.get_mix_rate()
	var bus := AudioServer.get_bus_index(MIC_BUS)
	if bus >= 0:
		for i in AudioServer.get_bus_effect_count(bus):
			var fx := AudioServer.get_bus_effect(bus, i)
			if fx is AudioEffectCapture:
				_capture = fx
	if _capture == null:
		push_warning("AudioService: на шине Mic нет AudioEffectCapture")

	_click_player = AudioStreamPlayer.new()
	_click_player.name = "ClickPlayer"
	_click_player.bus = SFX_BUS
	_click_player.stream = _make_click_stream()
	add_child(_click_player)


# --- Микрофон --------------------------------------------------------------

## Включить микрофон. В вебе вызывать только из обработчика пользовательского жеста.
func enable_mic() -> void:
	if _mic_player and _mic_player.playing:
		return
	if not ProjectSettings.get_setting("audio/driver/enable_input", false):
		push_warning("AudioService: audio/driver/enable_input выключен")
		mic_state = MicState.ERROR
		return
	if _mic_player == null:
		_mic_player = AudioStreamPlayer.new()
		_mic_player.name = "MicPlayer"
		_mic_player.stream = AudioStreamMicrophone.new()
		_mic_player.bus = MIC_BUS
		add_child(_mic_player)
	if _capture:
		_capture.clear_buffer()
	_frames_total = 0
	_silent_time = 0.0
	_mic_t0_usec = Time.get_ticks_usec()
	_mic_player.play()
	mic_state = MicState.STARTING


func disable_mic() -> void:
	if _mic_player:
		_mic_player.stop()
	rms_level = 0.0
	peak_level = 0.0
	level_changed.emit(0.0, 0.0)
	mic_state = MicState.OFF


func is_mic_on() -> bool:
	return mic_state in [MicState.STARTING, MicState.ACTIVE, MicState.SILENT]


func _process(delta: float) -> void:
	if is_calibrating:
		_update_calibration(delta)
	if _capture == null or _mic_player == null or not _mic_player.playing:
		return
	var available := _capture.get_frames_available()
	if available <= 0:
		_silent_time += delta
		if _silent_time > 2.0 and mic_state == MicState.STARTING:
			mic_state = MicState.SILENT
		return
	if _frames_total == 0:
		# первый блок: привязываем кадр 0 к реальному времени (с учётом длины блока)
		_mic_t0_usec = Time.get_ticks_usec() - int(available / _mix_rate * 1_000_000.0)
	var buf := _capture.get_buffer(available)
	if is_recording:
		_recorded.append_array(buf)
	_analyze(buf, delta)
	_frames_total += buf.size()


func _analyze(buf: PackedVector2Array, delta: float) -> void:
	var sum := 0.0
	var peak := 0.0
	var block := 256
	var n := buf.size()
	var i := 0
	while i < n:
		var end := mini(i + block, n)
		var bpeak := 0.0
		for j in range(i, end):
			var s := absf((buf[j].x + buf[j].y) * 0.5)
			sum += s * s
			bpeak = maxf(bpeak, s)
		peak = maxf(peak, bpeak)
		_detect_onset(bpeak, _frames_total + i)
		# медленная адаптация фонового уровня
		_noise_floor = lerpf(_noise_floor, bpeak, 0.02 if bpeak > _noise_floor else 0.2)
		i = end
	rms_level = sqrt(sum / maxf(n, 1))
	peak_level = maxf(peak, peak_level - delta * 1.5)
	level_changed.emit(rms_level, peak_level)
	if rms_level > 0.0005:
		_silent_time = 0.0
		mic_state = MicState.ACTIVE
	else:
		_silent_time += delta
		if _silent_time > 3.0:
			mic_state = MicState.SILENT


func _detect_onset(block_peak: float, frame_index: int) -> void:
	if not is_calibrating:
		return
	var t := _frame_to_sec(frame_index)
	if t - _last_onset_sec < ONSET_REFRACTORY_SEC:
		return
	if block_peak > ONSET_MIN_PEAK and block_peak > _noise_floor * ONSET_RATIO:
		_last_onset_sec = t
		_onsets_sec.append(t)


## Кадр микрофона → секунды по тем же часам, что и щелчки (ticks_usec).
func _frame_to_sec(frame_index: int) -> float:
	return (_mic_t0_usec / 1_000_000.0) + frame_index / _mix_rate


func _now_sec() -> float:
	return Time.get_ticks_usec() / 1_000_000.0


# --- Калибровка -------------------------------------------------------------

func start_calibration() -> void:
	enable_mic()
	is_calibrating = true
	_onsets_sec.clear()
	_cal_click_times.clear()
	_cal_index = 0
	_cal_timer = 0.6   # небольшая пауза перед первым щелчком
	_last_onset_sec = -10.0
	if has_node(^"/root/MenuMusic"):
		get_node(^"/root/MenuMusic").duck(true)


func cancel_calibration() -> void:
	if not is_calibrating:
		return
	is_calibrating = false
	_restore_music()


func _update_calibration(delta: float) -> void:
	_cal_timer -= delta
	if _cal_timer <= 0.0:
		if _cal_index < CAL_CLICKS:
			_play_click()
			_cal_timer += 60.0 / CAL_BPM
		else:
			_finish_calibration()
			return
	# сопоставляем пришедшие онсеты с ближайшими щелчками
	_match_hits()


func _play_click() -> void:
	_click_player.play()
	# момент, когда звук реально выйдет из колонок/наушников
	var t := _now_sec() + AudioServer.get_time_to_next_mix() + AudioServer.get_output_latency()
	_cal_click_times.append(t)
	_cal_index += 1
	calibration_click.emit(_cal_index, CAL_CLICKS)


var _matched_clicks: Dictionary = {}

func _match_hits() -> void:
	for onset in _onsets_sec:
		var best := -1
		var best_lag := INF
		for ci in _cal_click_times.size():
			var lag := (onset - _cal_click_times[ci]) * 1000.0
			if lag >= -80.0 and lag <= CAL_MAX_LAG_MS and absf(lag) < absf(best_lag):
				best = ci
				best_lag = lag
		if best >= 0 and not _matched_clicks.has(best):
			_matched_clicks[best] = best_lag
			calibration_hit.emit(best + 1, best_lag)
	_onsets_sec.clear()


func _finish_calibration() -> void:
	_match_hits()
	is_calibrating = false
	var lags: Array[float] = []
	for ci in _matched_clicks:
		if ci >= CAL_WARMUP_CLICKS:
			lags.append(_matched_clicks[ci])
	_matched_clicks.clear()
	_restore_music()
	if lags.size() < CAL_MIN_VALID:
		calibration_finished.emit(false, Session.lag_ms, lags.size())
		return
	lags.sort()
	var median := lags[lags.size() / 2]
	var result := clampi(roundi(median), Session.LAG_MIN_MS, Session.LAG_MAX_MS)
	Session.set_calibrated_lag(result)
	calibration_finished.emit(true, result, lags.size())


func _restore_music() -> void:
	if has_node(^"/root/MenuMusic"):
		get_node(^"/root/MenuMusic").duck(false)


func get_calibration_bpm() -> float:
	return CAL_BPM


# --- Запись (заглушка под геймплей) -----------------------------------------

func start_recording() -> void:
	enable_mic()
	_recorded = PackedVector2Array()
	is_recording = true


## Возвращает записанный голос как AudioStreamWAV (16 бит стерео).
func stop_recording() -> AudioStreamWAV:
	is_recording = false
	var data := PackedByteArray()
	data.resize(_recorded.size() * 4)
	for i in _recorded.size():
		data.encode_s16(i * 4, int(clampf(_recorded[i].x, -1.0, 1.0) * 32767.0))
		data.encode_s16(i * 4 + 2, int(clampf(_recorded[i].y, -1.0, 1.0) * 32767.0))
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.stereo = true
	wav.mix_rate = int(_mix_rate)
	wav.data = data
	return wav


# --- Утилиты ----------------------------------------------------------------

## Короткий «тик» метронома, генерируется в коде — без внешних файлов.
func _make_click_stream() -> AudioStreamWAV:
	var rate := 44100
	var length := int(rate * 0.06)
	var data := PackedByteArray()
	data.resize(length * 2)
	for i in length:
		var t := float(i) / rate
		var env := exp(-t * 70.0)
		var s := (sin(TAU * 1760.0 * t) * 0.7 + sin(TAU * 880.0 * t) * 0.3) * env
		data.encode_s16(i * 2, int(s * 30000.0))
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = rate
	wav.stereo = false
	wav.data = data
	return wav
