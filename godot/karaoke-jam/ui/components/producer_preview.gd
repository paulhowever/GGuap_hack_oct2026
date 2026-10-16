class_name ProducerPreview
extends CharacterPreview
## Продюсер-заглушка: та же модель Gvozd, перекрашенная в tint. Наряды из
## гардероба на него не надеваются: у Outfit в producer_preview.tscn
## выключен follow_session, а apply_outfit() никто не вызывает.

## Цвет, на который умножается материал модели.
@export var tint: Color = Color(0.55, 0.8, 1.0)
## Доля длины анимации, с которой она начинается (чтобы не двигаться синхронно с персонажем).
@export_range(0.0, 1.0) var anim_phase: float = 0.5


func _ready() -> void:
	super()
	_apply_tint()
	if _anim.current_animation != &"":
		_anim.seek(_anim.current_animation_length * anim_phase, true)


## Перекрашивает модель: копии материалов, чтобы не задеть персонажа игрока.
func _apply_tint() -> void:
	for node in _model.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null:
			continue
		for s in mi.mesh.get_surface_count():
			var mat := mi.get_active_material(s) as BaseMaterial3D
			if mat == null:
				continue
			mat = mat.duplicate() as BaseMaterial3D
			mat.albedo_color = tint
			mi.set_surface_override_material(s, mat)
