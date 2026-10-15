extends Control
## Стартовый экран: фон-студия, винил-логотип, меню (Петь / Настройки),
## верхняя и нижняя панели, модальные окна (первый запуск, калибровка, настройки).
## В вебе страница уже получила клик на оверлее shell.html, так что звук можно
## запускать сразу. Вне веба — тоже сразу.

const SELECT_SCENE := "res://scenes/select/select.tscn"


@onready var _logo: Control = %VinylLogo
@onready var _sing: RhythmMenuButton = %SingButton
@onready var _settings_btn: RhythmMenuButton = %SettingsButton
@onready var _gear: Button = %GearButton
@onready var _nick: Label = %NickLabel
@onready var _lag_label: Label = %LagLabel
@onready var _calibrate_link: Button = %CalibrateLink
@onready var _headphones_hint: Label = %HeadphonesHint
@onready var _first_run: ModalPanel = %FirstRunPanel
@onready var _calibration: ModalPanel = %CalibrationPanel
@onready var _settings: ModalPanel = %SettingsPanel
@onready var _fade: ColorRect = %Fade

var _leaving: bool = false


func _ready() -> void:
	WebShell.sync_nickname_to_session()
	_register_player()
	Session.nickname_changed.connect(func(_n: String) -> void: _register_player())
	_sing.pressed.connect(_on_sing)
	_settings_btn.pressed.connect(_settings.open)
	_gear.pressed.connect(_settings.open)
	_calibrate_link.pressed.connect(_calibration.open)
	_first_run.calibrate_chosen.connect(_calibration.open)
	_first_run.skipped.connect(_focus_menu)
	_calibration.closed.connect(_focus_menu)
	_settings.closed.connect(_focus_menu)
	_settings.calibrate_requested.connect(_calibration.open)
	# пока открыто модальное окно, клавиатурный фокус не уходит в меню под ним
	for m: ModalPanel in [_first_run, _calibration, _settings]:
		m.opened.connect(_update_focus_lock)
		m.closed.connect(_update_focus_lock)
	Session.nickname_changed.connect(func(_n: String) -> void: _refresh_bars())
	Session.lag_changed.connect(func(_v: int) -> void: _refresh_bars())
	Session.headphones_changed.connect(func(_v: bool) -> void: _refresh_bars())
	_refresh_bars()

	MenuMusic.start()
	_play_intro()

	if Session.is_first_run():
		await get_tree().create_timer(0.9).timeout
		_first_run.open()
	else:
		_focus_menu()


## POST /players: ник привязывается к client_id движка (для таблицы результатов).
## Ошибка сети не мешает играть — только предупреждение.
func _register_player() -> void:
	var r: Dictionary = await Api.register_player(Session.nickname)
	if not r.ok and r.error != "no_client_id":
		push_warning("Boot: не удалось зарегистрировать игрока (%s)" % r.error)


func _play_intro() -> void:
	_fade.visible = true
	_fade.modulate.a = 1.0
	create_tween().tween_property(_fade, "modulate:a", 0.0, 0.6)
	_logo.play_intro(0.1)
	# позиции кнопок известны только после раскладки контейнеров
	await get_tree().process_frame
	_sing.play_intro(0.35)
	_settings_btn.play_intro(0.47)


func _focus_menu() -> void:
	if not _any_modal_open():
		_sing.grab_focus.call_deferred()


## Отключает фокус у всего меню под модальным окном (focus_behavior_recursive,
## Godot 4.5+), чтобы стрелки/Tab ходили только внутри открытого окна.
func _update_focus_lock() -> void:
	var behavior := Control.FOCUS_BEHAVIOR_DISABLED if _any_modal_open() \
		else Control.FOCUS_BEHAVIOR_INHERITED
	for c: Control in [$Center, $TopBar, $BottomBar]:
		c.focus_behavior_recursive = behavior


func _any_modal_open() -> bool:
	return _first_run.is_open or _calibration.is_open or _settings.is_open


func _refresh_bars() -> void:
	_nick.text = Session.nickname
	_lag_label.text = "Задержка: %d мс%s" % [Session.lag_ms, "" if Session.is_calibrated else " (не откалибровано)"]
	_headphones_hint.text = "Наушники подключены" if Session.headphones_confirmed \
		else "Пойте в проводных наушниках"


func _on_sing() -> void:
	if _leaving:
		return
	_leaving = true
	_fade.visible = true
	var tw := create_tween()
	tw.tween_property(_fade, "modulate:a", 1.0, 0.35)
	await tw.finished
	if ResourceLoader.exists(SELECT_SCENE):
		get_tree().change_scene_to_file(SELECT_SCENE)
	else:
		push_warning("Boot: сцена выбора песни ещё не создана")
		_leaving = false
		create_tween().tween_property(_fade, "modulate:a", 0.0, 0.3)


func _unhandled_input(event: InputEvent) -> void:
	if _any_modal_open():
		return
	if event.is_action_pressed(&"ui_cancel"):
		_settings.open()
		get_viewport().set_input_as_handled()
	elif event.is_action_pressed(&"ui_accept") and get_viewport().gui_get_focus_owner() == null:
		_sing.grab_focus()
		get_viewport().set_input_as_handled()
