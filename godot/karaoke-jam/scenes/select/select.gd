extends Control
## Заглушка экрана выбора песни. Esc / «Назад» — вернуться в меню.

const BOOT_SCENE := "res://scenes/boot/boot.tscn"


func _ready() -> void:
	%BackButton.pressed.connect(_back)
	%BackButton.grab_focus.call_deferred()
	# Boot уходит в затемнение цветом Fade — появляемся из того же цвета,
	# иначе фон «выпрыгивает» резко.
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)


func _back() -> void:
	get_tree().change_scene_to_file(BOOT_SCENE)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		_back()
