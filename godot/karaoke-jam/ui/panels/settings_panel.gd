extends ModalPanel
## Настройки: громкость музыки, задержка (калибровка + ±10 мс), ник, наушники.

signal calibrate_requested

@onready var _volume: HSlider = %VolumeSlider
@onready var _volume_value: Label = %VolumeValue
@onready var _lag_value: Label = %LagValue
@onready var _lag_minus: Button = %LagMinus
@onready var _lag_plus: Button = %LagPlus
@onready var _calibrate: Button = %CalibrateButton
@onready var _nick: LineEdit = %NickEdit
@onready var _headphones: CheckBox = %HeadphonesCheck
@onready var _close: Button = %CloseButton


func _ready() -> void:
	super._ready()
	_volume.value_changed.connect(_on_volume)
	_lag_minus.pressed.connect(_nudge.bind(-10))
	_lag_plus.pressed.connect(_nudge.bind(10))
	_calibrate.pressed.connect(func() -> void:
		await close()
		calibrate_requested.emit())
	_nick.text_submitted.connect(func(_t: String) -> void: _apply_nick())
	_nick.focus_exited.connect(_apply_nick)
	_headphones.toggled.connect(func(on: bool) -> void:
		Session.headphones_confirmed = on
		Session.save_settings())
	_close.pressed.connect(close)
	Session.lag_changed.connect(func(_v: int) -> void: _refresh())
	_setup_focus_neighbors()


## Явные соседи для клавиатуры: между кнопками стоит Label, и автопоиск
## по геометрии мог перескакивать мимо «−10».
func _setup_focus_neighbors() -> void:
	_lag_minus.focus_neighbor_right = _lag_minus.get_path_to(_lag_plus)
	_lag_plus.focus_neighbor_left = _lag_plus.get_path_to(_lag_minus)
	_lag_plus.focus_neighbor_right = _lag_plus.get_path_to(_calibrate)
	_calibrate.focus_neighbor_left = _calibrate.get_path_to(_lag_plus)
	_volume.focus_neighbor_bottom = _volume.get_path_to(_lag_minus)
	_lag_minus.focus_neighbor_top = _lag_minus.get_path_to(_volume)
	_lag_minus.focus_neighbor_bottom = _lag_minus.get_path_to(_nick)
	_nick.focus_neighbor_top = _nick.get_path_to(_lag_minus)


func _on_opened() -> void:
	_refresh()


func _on_closing() -> void:
	_apply_nick()
	Session.save_settings()


func _refresh() -> void:
	_volume.set_value_no_signal(Session.music_volume * 100.0)
	_volume_value.text = "%d%%" % roundi(Session.music_volume * 100.0)
	_lag_value.text = "%d мс%s" % [Session.lag_ms, "" if Session.is_calibrated else " (по умолч.)"]
	_nick.text = Session.nickname
	_headphones.set_pressed_no_signal(Session.headphones_confirmed)


func _on_volume(v: float) -> void:
	Session.music_volume = v / 100.0
	_volume_value.text = "%d%%" % roundi(v)


func _nudge(d: int) -> void:
	Session.lag_ms += d
	Session.save_settings()
	_refresh()


func _apply_nick() -> void:
	if _nick.text.strip_edges() != Session.nickname:
		Session.nickname = _nick.text
		Session.save_settings()
		_nick.text = Session.nickname
