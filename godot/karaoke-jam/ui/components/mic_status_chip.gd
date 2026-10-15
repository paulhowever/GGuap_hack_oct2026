class_name MicStatusChip
extends PanelContainer
## «Чип» статуса микрофона: иконка + текст + полоска уровня.
## Клик — включить/выключить микрофон (жест пользователя нужен браузеру).

const MicState = preload("res://autoload/audio_service.gd").MicState


@export var color_ok: Color = Color("#5FD3BC")
@export var color_warn: Color = Color("#FFC861")
@export var color_off: Color = Color(0.953, 0.902, 0.827, 0.45)
@export var color_error: Color = Color("#FF5D5D")

@onready var _icon: TextureRect = %Icon
@onready var _label: Label = %StateLabel
@onready var _level: ProgressBar = %Level


func _ready() -> void:
	theme_type_variation = &"Chip"
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	tooltip_text = "Нажмите, чтобы включить микрофон"
	gui_input.connect(_on_gui_input)
	AudioService.mic_state_changed.connect(_refresh)
	AudioService.level_changed.connect(_on_level)
	_refresh(AudioService.mic_state)


func _on_gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if AudioService.is_mic_on():
			# во время калибровки микрофон нужен — не выключаем
			if not AudioService.is_calibrating:
				AudioService.disable_mic()
		else:
			AudioService.enable_mic()
		accept_event()


func _on_level(rms: float, _peak: float) -> void:
	_level.value = clampf(sqrt(rms) * 2.2, 0.0, 1.0)


func _refresh(state: int) -> void:
	var c := color_off
	var t := "Микрофон выкл."
	match state:
		MicState.STARTING:
			c = color_warn
			t = "Микрофон…"
		MicState.ACTIVE:
			c = color_ok
			t = "Микрофон"
		MicState.SILENT:
			c = color_warn
			t = "Тишина в микрофоне"
		MicState.ERROR:
			c = color_error
			t = "Нет доступа к микрофону"
	_icon.modulate = c
	_label.text = t
	_label.add_theme_color_override(&"font_color", c)
	tooltip_text = "Нажмите, чтобы выключить микрофон" if AudioService.is_mic_on() \
		else "Нажмите, чтобы включить микрофон"
	_level.visible = state in [MicState.ACTIVE, MicState.SILENT, MicState.STARTING]
