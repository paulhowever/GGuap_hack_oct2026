extends Control
## Экран результата: Session.last_result (контракт TakeResult).
## Итог, оценка, точность по высоте/ритму, разбор строк с советами,
## место в таблице (блок скрыт, если leaderboard == null).

const SELECT_SCENE := "res://scenes/select/select.tscn"
const GAME_SCENE := "res://scenes/game/game.tscn"
const MAX_SCORE := 10000.0
const FILL_SEC := 1.4
const S_SHADER := preload("res://ui/shaders/grade_s.gdshader")
## Доля font_size, которую занимает заглавная буква (типично 0.7–0.75).
const CAP_HEIGHT := 0.72
## Цвета рангов: S — золото, A..D — от голубого проекта к красному.
const GRADE_COLORS := {
	"S": Color(1.0, 0.82, 0.35),      # золото
	"A": Color(0.373, 0.827, 0.737),  # #5FD3BC
	"B": Color(0.85, 0.83, 0.36),     # жёлто-лаймовый
	"C": Color(1.0, 0.6, 0.25),       # оранжевый
	"D": Color(1.0, 0.365, 0.365),    # #FF5D5D
}

@onready var _ring: ScoreRing = %ScoreRing
@onready var _percent: Label = %PercentLabel
@onready var _total: Label = %TotalLabel
@onready var _grade: Label = %GradeLabel
## «Удары» ранга под бит музыки меню (включается после появления ранга).
@onready var _grade_beat: BeatReactor = %GradeBeat
@onready var _details: Label = %DetailsLabel
@onready var _lines: VBoxContainer = %LinesList
@onready var _board: Label = %BoardLabel
@onready var _warn: Label = %WarnLabel

var _leaving: bool = false


func _ready() -> void:
	%AgainButton.pressed.connect(_go.bind(GAME_SCENE))
	%SelectButton.pressed.connect(_go.bind(SELECT_SCENE))
	%AgainButton.grab_focus.call_deferred()
	MenuMusic.start()   # музыка меню задаёт бит для ударов ранга
	create_tween().tween_property(%Fade, "modulate:a", 0.0, 0.35)
	_fill(Session.last_result)


func _fill(r: Dictionary) -> void:
	var score: Dictionary = r.get("score", {}) if r.get("score") is Dictionary else {}
	var total := clampi(int(score.get("total", 0)), 0, int(MAX_SCORE))
	_details.text = "Высота %d%%   ·   Ритм %d%%   ·   Бонусы %d%%" % [
		roundi(float(score.get("pitch_pct", 0))), roundi(float(score.get("rhythm_pct", 0))),
		roundi(float(score.get("extras_pct", 0)))]
	_animate_score(float(total), str(score.get("grade", "—")))

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


## Кольцо заполняется до процента, процент и очки «набегают»,
## затем ранг появляется с «попом».
func _animate_score(total: float, grade: String) -> void:
	_ring.value = 0.0
	_set_progress(0.0, total)
	_grade.text = grade
	_grade.modulate.a = 0.0
	_style_grade(grade)
	_grade_beat.enabled = false
	var tw := create_tween()
	tw.tween_method(_set_progress.bind(total), 0.0, 1.0, FILL_SEC) \
		.set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_callback(_pop_grade)


## S — статичный золотой градиент (шейдер), остальные ранги — сплошной цвет.
func _style_grade(grade: String) -> void:
	if grade == "S":
		var mat := ShaderMaterial.new()
		mat.shader = S_SHADER
		_grade.material = mat
		_grade.add_theme_color_override(&"font_color", Color.WHITE)
	else:
		_grade.material = null
		_grade.add_theme_color_override(&"font_color", GRADE_COLORS.get(grade, Color.WHITE))


## Растягивает градиент S ровно по высоте заглавной буквы (а не всей строки
## с пустыми ascent/descent), иначе перепад цвета почти не виден.
func _fit_grade_gradient() -> void:
	var mat := _grade.material as ShaderMaterial
	if mat == null:
		return
	var font := _grade.get_theme_font(&"font")
	var fs := _grade.get_theme_font_size(&"font_size")
	var text_h := font.get_height(fs)
	# смещение строки внутри Label с учётом вертикального выравнивания
	var top := (_grade.size.y - text_h) * (float(_grade.vertical_alignment) * 0.5) \
		if _grade.vertical_alignment != VERTICAL_ALIGNMENT_FILL else 0.0
	var baseline := top + font.get_ascent(fs)
	mat.set_shader_parameter(&"grad_top", baseline - fs * CAP_HEIGHT)
	mat.set_shader_parameter(&"grad_bottom", baseline)


func _set_progress(k: float, total: float) -> void:
	var pts := total * k
	_ring.value = pts / MAX_SCORE * 100.0
	_percent.text = "%.1f%%" % _ring.value
	_total.text = "%d очков" % roundi(pts)


## «Поп» ранга; после него масштабом управляет BeatReactor (удары под бит).
func _pop_grade() -> void:
	_grade.pivot_offset = _grade.size * 0.5
	_fit_grade_gradient()   # к этому моменту раскладка Label уже посчитана
	_grade.scale = Vector2.ONE * 1.6
	var tw := create_tween().set_parallel()
	tw.tween_property(_grade, "modulate:a", 1.0, 0.2)
	tw.tween_property(_grade, "scale", Vector2.ONE, 0.35) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.chain().tween_callback(func() -> void: _grade_beat.enabled = true)


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
