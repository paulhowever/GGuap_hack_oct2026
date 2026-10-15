extends ModalPanel
## Калибровка задержки: 10 щелчков метронома, игрок хлопает/говорит «та».
## AudioService ловит онсеты в микрофоне и считает медиану задержки.
## После — результат и ручная подстройка ±10 мс.

signal calibration_done(lag_ms: int)


enum Step { INTRO, RUNNING, RESULT, FAILED }

@onready var _title: Label = %CalTitle
@onready var _hint: Label = %CalHint
@onready var _beat_ring: Control = %BeatRing
@onready var _dots: HBoxContainer = %Dots
@onready var _result: Label = %ResultValue
@onready var _result_box: Control = %ResultBox
@onready var _start_btn: Button = %StartButton
@onready var _done_btn: Button = %DoneButton
@onready var _minus_btn: Button = %MinusButton
@onready var _plus_btn: Button = %PlusButton
@onready var _level: ProgressBar = %MicLevel

var _step: Step = Step.INTRO
var _ring_flash: float = 0.0
var _dot_nodes: Array[ColorRect] = []


func _ready() -> void:
	super._ready()
	_start_btn.pressed.connect(_start)
	_done_btn.pressed.connect(_finish)
	_minus_btn.pressed.connect(_nudge.bind(-10))
	_plus_btn.pressed.connect(_nudge.bind(10))
	AudioService.calibration_click.connect(_on_click)
	AudioService.calibration_hit.connect(_on_hit)
	AudioService.calibration_finished.connect(_on_finished)
	AudioService.level_changed.connect(func(rms: float, _p: float) -> void:
		_level.value = clampf(sqrt(rms) * 2.2, 0.0, 1.0))
	_beat_ring.draw.connect(_draw_ring)
	_build_dots()


func _on_opened() -> void:
	_set_step(Step.INTRO)
	# Микрофон включаем сразу (это обработчик клика — браузер разрешит).
	AudioService.enable_mic()


func _on_closing() -> void:
	AudioService.cancel_calibration()


func _build_dots() -> void:
	for c in _dots.get_children():
		c.queue_free()
	_dot_nodes.clear()
	for i in AudioService.CAL_CLICKS:
		var d := ColorRect.new()
		d.custom_minimum_size = Vector2(26, 26)
		d.color = Color(0.953, 0.902, 0.827, 0.12)
		_dots.add_child(d)
		_dot_nodes.append(d)


func _set_step(s: Step) -> void:
	_step = s
	_start_btn.visible = s in [Step.INTRO, Step.FAILED]
	_done_btn.visible = s == Step.RESULT
	_result_box.visible = s == Step.RESULT
	_beat_ring.visible = s in [Step.INTRO, Step.RUNNING]
	match s:
		Step.INTRO:
			_title.text = "Калибровка задержки"
			_hint.text = "Наденьте наушники. Услышите 10 щелчков —\nхлопайте в ладоши или говорите «та» точно вместе с ними."
			_start_btn.text = "Начать"
			_build_dots()
		Step.RUNNING:
			_title.text = "Хлопайте в такт!"
			_hint.text = "Первые два щелчка — чтобы поймать ритм."
		Step.RESULT:
			_title.text = "Готово!"
			_hint.text = "Если ощущается, что голос «опаздывает» — подстройте вручную."
			_refresh_result()
		Step.FAILED:
			_title.text = "Не получилось расслышать"
			_hint.text = "Хлопайте громче и ближе к микрофону.\nПроверьте, что браузер дал доступ к микрофону."
			_start_btn.text = "Ещё раз"
	if is_open:
		var f: Control = _start_btn if _start_btn.visible else _done_btn
		f.grab_focus.call_deferred()


func _start() -> void:
	_build_dots()
	_set_step(Step.RUNNING)
	AudioService.start_calibration()


func _on_click(index: int, _total: int) -> void:
	_ring_flash = 1.0
	if index - 1 < _dot_nodes.size():
		_dot_nodes[index - 1].color = Color(0.953, 0.902, 0.827, 0.35)


func _on_hit(index: int, _lag: float) -> void:
	if index - 1 < _dot_nodes.size():
		var ok := index > AudioService.CAL_WARMUP_CLICKS
		_dot_nodes[index - 1].color = Color("#5FD3BC") if ok else Color("#FFC861")


func _on_finished(success: bool, _lag_ms: int, _hits: int) -> void:
	if not is_open:
		return
	_set_step(Step.RESULT if success else Step.FAILED)


func _nudge(delta_ms: int) -> void:
	Session.lag_ms += delta_ms
	Session.save_settings()
	_refresh_result()


func _refresh_result() -> void:
	_result.text = "%d мс" % Session.lag_ms


func _finish() -> void:
	calibration_done.emit(Session.lag_ms)
	close()


func _process(delta: float) -> void:
	if not visible:
		return
	_ring_flash = move_toward(_ring_flash, 0.0, delta * 4.0)
	_beat_ring.queue_redraw()


func _draw_ring() -> void:
	var c := _beat_ring.size * 0.5
	var r := minf(c.x, c.y) - 8.0
	var accent := Color("#FF7A3D")
	_beat_ring.draw_arc(c, r, 0.0, TAU, 96, Color(0.953, 0.902, 0.827, 0.12), 6.0, true)
	if _ring_flash > 0.0:
		_beat_ring.draw_circle(c, r * (0.55 + 0.45 * _ring_flash), Color(accent, 0.18 * _ring_flash))
		_beat_ring.draw_arc(c, r, 0.0, TAU, 96, Color(accent, _ring_flash), 8.0, true)
	_beat_ring.draw_circle(c, r * 0.22, accent if _step == Step.RUNNING else Color(accent, 0.5))
