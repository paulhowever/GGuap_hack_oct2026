extends Control
## Стартовый экран: фон-студия, винил-логотип, меню (Петь / Настройки),
## верхняя и нижняя панели, модальные окна (первый запуск, калибровка, настройки).
## В вебе страница уже получила клик на оверлее shell.html, так что звук можно
## запускать сразу. Вне веба — тоже сразу.

const SELECT_SCENE := "res://scenes/select/select.tscn"
## Наряд отправляется на бэкенд не на каждый клик, а через паузу после последнего.
const AVATAR_SYNC_DELAY := 1.5


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
@onready var _customize: CustomizePanel = %CustomizePanel
@onready var _character: CharacterPreview = %CharacterPreview
@onready var _menu: Control = $Center/Row/Menu
@onready var _fade: ColorRect = %Fade
@onready var _loading_label: Label = %LoadingLabel

var _leaving: bool = false
var _avatar_timer: Timer
## Пока идёт заставка с прогревом шейдеров, гардероб не открывается.
var _loading: bool = true


func _ready() -> void:
	WebShell.sync_nickname_to_session()
	_register_player()
	Session.nickname_changed.connect(func(_n: String) -> void: _register_player())
	_avatar_timer = Timer.new()
	_avatar_timer.one_shot = true
	_avatar_timer.wait_time = AVATAR_SYNC_DELAY
	_avatar_timer.timeout.connect(_register_player)
	add_child(_avatar_timer)
	Session.outfit_changed.connect(func(_s: StringName, _i: StringName) -> void: _avatar_timer.start())
	_sing.pressed.connect(_on_sing)
	_settings_btn.pressed.connect(_settings.open)
	_gear.pressed.connect(_settings.open)
	_calibrate_link.pressed.connect(_calibration.open)
	_first_run.calibrate_chosen.connect(_calibration.open)
	_first_run.skipped.connect(_focus_menu)
	_calibration.closed.connect(_focus_menu)
	_settings.closed.connect(_focus_menu)
	_settings.calibrate_requested.connect(_calibration.open)
	# гардероб: клик по персонажу (без перетаскивания) открывает окно
	_customize.source_preview = _character
	_character.clicked.connect(_open_customize)
	_customize.closing.connect(_show_menu.bind(true))
	_customize.closed.connect(_focus_menu)
	_menu.offset_transform_enabled = true
	# пока открыто модальное окно, клавиатурный фокус не уходит в меню под ним
	for m: ModalPanel in [_first_run, _calibration, _settings, _customize]:
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


## POST /players: ник и наряд привязываются к client_id движка (для таблицы
## результатов). Ошибка сети не мешает играть — только предупреждение.
func _register_player() -> void:
	var r: Dictionary = await Api.register_player(Session.nickname, Session.get_avatar())
	if not r.ok and r.error != "no_client_id":
		push_warning("Boot: не удалось зарегистрировать игрока (%s)" % r.error)


func _play_intro() -> void:
	_fade.visible = true
	_fade.modulate.a = 1.0
	await _warm_up_with_loading()
	_loading = false
	create_tween().tween_property(_fade, "modulate:a", 0.0, 0.6)
	_logo.play_intro(0.1)
	# позиции кнопок известны только после раскладки контейнеров
	await get_tree().process_frame
	_sing.play_intro(0.35)
	_settings_btn.play_intro(0.47)


## Под заставкой «Загрузка» один раз рисуем гардероб, чтобы WebGL скомпилировал
## его шейдеры сейчас, а не при первом открытии (иначе — подвисание на клике).
func _warm_up_with_loading() -> void:
	_loading_label.visible = true
	_loading_label.modulate.a = 1.0
	var pulse := create_tween().set_loops()
	pulse.tween_property(_loading_label, "modulate:a", 0.35, 0.5)
	pulse.tween_property(_loading_label, "modulate:a", 1.0, 0.5)
	# сначала показываем надпись, потом грузим: компиляция шейдеров блокирует кадр
	await RenderingServer.frame_post_draw
	await _customize.warm_up()
	pulse.kill()
	# надпись — дочерний узел Fade и гаснет вместе с ним
	_loading_label.modulate.a = 1.0


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
	return _first_run.is_open or _calibration.is_open or _settings.is_open \
		or _customize.is_open


func _open_customize() -> void:
	if _leaving or _loading or _any_modal_open():
		return
	_show_menu(false)
	_customize.open()


## Меню уезжает вправо, пока открыт гардероб, и возвращается при закрытии.
## offset_transform — визуальный сдвиг, раскладку HBox он не трогает.
func _show_menu(on: bool) -> void:
	var tw := create_tween().set_parallel()
	tw.tween_property(_menu, ^"modulate:a", 1.0 if on else 0.0, 0.3 if on else 0.2)
	tw.tween_property(_menu, ^"offset_transform_position",
		Vector2.ZERO if on else Vector2(220.0, 0.0), 0.45) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT if on else Tween.EASE_IN)


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
