extends ModalPanel
## Первый запуск: приветствие по нику, просьба надеть проводные наушники,
## предложение откалибровать задержку (можно пропустить).

signal calibrate_chosen
signal skipped

@onready var _greeting: Label = %Greeting
@onready var _headphones: CheckBox = %HeadphonesCheck
@onready var _calibrate: Button = %CalibrateButton
@onready var _skip: Button = %SkipButton


func _ready() -> void:
	super._ready()
	allow_close = false
	_calibrate.pressed.connect(_choose.bind(true))
	_skip.pressed.connect(_choose.bind(false))
	_headphones.toggled.connect(func(on: bool) -> void:
		Session.headphones_confirmed = on)


func _on_opened() -> void:
	_greeting.text = "Привет, %s!" % Session.nickname
	_headphones.set_pressed_no_signal(Session.headphones_confirmed)


func _choose(calibrate: bool) -> void:
	Session.mark_first_run_done()
	await close()
	if calibrate:
		calibrate_chosen.emit()
	else:
		skipped.emit()
