class_name ConfirmPanel
extends ModalPanel
## Подтверждение действия: заголовок, текст и две кнопки.
## `if await confirm.ask("Заголовок", "Текст", "Да"):` — true только по «Да»;
## «Отмена», Esc и клик по затемнению дают false.

## Ответ пользователя (true — «Да»).
signal answered(ok: bool)

var _answer: bool = false

@onready var _title: Label = %ConfirmTitle
@onready var _text: Label = %ConfirmText
@onready var _ok: Button = %ConfirmOk
@onready var _cancel: Button = %ConfirmCancel


func _ready() -> void:
	super._ready()
	_ok.pressed.connect(_finish.bind(true))
	_cancel.pressed.connect(_finish.bind(false))
	closed.connect(func() -> void: answered.emit(_answer))


func ask(title: String, text: String, ok_text: String = "Да", cancel_text: String = "Отмена") -> bool:
	_title.text = title
	_text.text = text
	_ok.text = ok_text
	_cancel.text = cancel_text
	_answer = false
	open()
	var ok: bool = await answered
	return ok  # true — «Да»


func _finish(ok: bool) -> void:
	_answer = ok
	close()
