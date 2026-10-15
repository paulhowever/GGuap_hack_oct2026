extends Control
## Экран результата: Session.last_result (контракт TakeResult).
## Итог, оценка, точность по высоте/ритму, разбор строк с советами,
## место в таблице (блок скрыт, если leaderboard == null).

const SELECT_SCENE := "res://scenes/select/select.tscn"
const GAME_SCENE := "res://scenes/game/game.tscn"

@onready var _total: Label = %TotalLabel
@onready var _grade: Label = %GradeLabel
@onready var _details: Label = %DetailsLabel
@onready var _lines: VBoxContainer = %LinesList
@onready var _board: Label = %BoardLabel
@onready var _warn: Label = %WarnLabel

var _leaving: bool = false


func _ready() -> void:
	%AgainButton.pressed.connect(_go.bind(GAME_SCENE))
	%SelectButton.pressed.connect(_go.bind(SELECT_SCENE))
	%AgainButton.grab_focus.call_deferred()
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	_fill(Session.last_result)


func _fill(r: Dictionary) -> void:
	var score: Dictionary = r.get("score", {}) if r.get("score") is Dictionary else {}
	var total := int(score.get("total", 0))
	_grade.text = str(score.get("grade", "—"))
	_details.text = "Высота %d%%   ·   Ритм %d%%   ·   Бонусы %d%%" % [
		roundi(float(score.get("pitch_pct", 0))), roundi(float(score.get("rhythm_pct", 0))),
		roundi(float(score.get("extras_pct", 0)))]
	# счёт «набегает»
	create_tween().tween_method(func(v: float) -> void: _total.text = str(roundi(v)),
		0.0, float(total), 1.2).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)

	for line in r.get("lines", []):
		if not line is Dictionary:
			continue
		var l := Label.new()
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.add_theme_font_size_override(&"font_size", 24)
		var tip = line.get("tip")
		l.text = "«%s» — %s (%d)%s" % [line.get("text", ""), line.get("grade", ""),
			int(line.get("score", 0)), ("\n   " + str(tip)) if tip != null and str(tip) != "" else ""]
		_lines.add_child(l)

	var lb = r.get("leaderboard")
	_board.visible = lb is Dictionary
	if lb is Dictionary:
		_board.text = "Место %d из %d%s" % [int(lb.get("rank", 0)), int(lb.get("of", 0)),
			"  ·  личный рекорд!" if lb.get("personal_best", false) else ""]

	var integrity = r.get("integrity")
	_warn.visible = integrity is Dictionary and str(integrity.get("status", "ok")) != "ok"
	if _warn.visible:
		_warn.text = "Запись не попала в таблицу: проверка честности не пройдена."


func _go(scene: String) -> void:
	if _leaving:
		return
	_leaving = true
	var tw := create_tween()
	tw.tween_property(%Fade, "modulate:a", 1.0, 0.3)
	await tw.finished
	get_tree().change_scene_to_file(scene)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed(&"ui_cancel"):
		get_viewport().set_input_as_handled()
		_go(SELECT_SCENE)
