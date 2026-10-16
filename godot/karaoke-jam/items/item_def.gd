class_name ItemDef
extends Resource
## Описание предмета гардероба: что это, в какой слот и на какую кость надевается.
## Новый предмет: сцена res://items/<id>.tscn (корень Node3D, размеры в
## единицах модели персонажа, начало координат — точка крепления, «вперёд» — +Z)
## и новый элемент ItemDef в res://items/catalog.tres. Кнопка в гардеробе
## появится сама, превью в кнопке масштабируется автоматически.

@export var id: StringName
@export var display_name: String = ""
## Слот на персонаже: в одном слоте одновременно может быть только один предмет.
@export var slot: StringName
## Модель предмета.
@export var scene: PackedScene
## Кость скелета персонажа, к которой крепится предмет (BoneAttachment3D).
@export var bone: StringName = &"DEF_BOODY"
## Смещение относительно кости — в единицах модели (масштаб Armature убирается
## автоматически), по осям кости.
@export var offset_position: Vector3 = Vector3.ZERO
@export var offset_rotation_deg: Vector3 = Vector3.ZERO
@export var offset_scale: float = 1.0
## Наклон модели в кнопке гардероба, градусы.
@export var preview_rotation_deg: Vector3 = Vector3.ZERO


## Локальный transform предмета относительно кости (в единицах модели).
func get_offset() -> Transform3D:
	var rot := Basis.from_euler(offset_rotation_deg * (PI / 180.0))
	return Transform3D(rot.scaled(Vector3.ONE * offset_scale), offset_position)
