extends Control
## Фон «студия»: шейдер + боковые эквалайзеры + всплывающие ноты.
## Отвечает только за подгонку частиц под размер экрана.

## Сколько акцентных эмиттеров крутится по кругу. restart() у one-shot
## эмиттера мгновенно убивает его живые частицы, поэтому каждый такт
## запускаем следующий из пула — предыдущие ноты спокойно догорают.
const ACCENT_POOL_SIZE := 4

@onready var _notes: CPUParticles2D = %Notes
@onready var _notes_accent: CPUParticles2D = %NotesAccent

var _accent_pool: Array[CPUParticles2D] = []
var _accent_next: int = 0


func _ready() -> void:
	_build_accent_pool()
	resized.connect(_fit_particles)
	_fit_particles()
	var music := get_node_or_null(^"/root/MenuMusic")
	if music:
		music.measure.connect(_on_measure)


func _build_accent_pool() -> void:
	if _notes_accent == null:
		return
	_accent_pool.append(_notes_accent)
	for i in ACCENT_POOL_SIZE - 1:
		var p := _notes_accent.duplicate() as CPUParticles2D
		p.unique_name_in_owner = false
		p.name = "%s%d" % [_notes_accent.name, i + 2]
		p.emitting = false
		add_child(p)
		move_child(p, _notes_accent.get_index() + i + 1)
		_accent_pool.append(p)


func _fit_particles() -> void:
	var all: Array[CPUParticles2D] = [_notes]
	all.append_array(_accent_pool)
	for p: CPUParticles2D in all:
		if p == null:
			continue
		p.position = Vector2(size.x * 0.5, size.y + 40.0)
		p.emission_rect_extents = Vector2(size.x * 0.5, 10.0)


## На сильную долю — небольшой «выброс» акцентных нот.
func _on_measure(_i: int) -> void:
	if _accent_pool.is_empty() or not is_visible_in_tree():
		return
	_accent_pool[_accent_next].restart()
	_accent_next = (_accent_next + 1) % _accent_pool.size()
