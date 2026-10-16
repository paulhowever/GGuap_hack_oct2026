class_name CharacterOutfit
extends Node
## Надевает на персонажа предметы из Session.outfit: на каждый занятый слот —
## BoneAttachment3D на кость из ItemDef, внутри — модель предмета.
## Достаточно положить этот узел рядом с моделью персонажа (дочерним к её
## корню) — скелет найдётся сам, наряд появится и будет обновляться при смене
## в гардеробе.

## Скелет персонажа (пусто — первый Skeleton3D внутри родителя).
@export var skeleton: Skeleton3D
## Корень модели: в его единицах заданы смещения предметов (ItemDef.offset_*).
## Пусто — родитель этого узла.
@export var model_root: Node3D
## Следить за Session.outfit (выключить — наряд задаётся через apply_outfit()).
@export var follow_session: bool = true

## slot → BoneAttachment3D с надетым предметом.
var _attached: Dictionary[StringName, BoneAttachment3D] = {}
## slot → item_id надетого предмета.
var _equipped: Dictionary[StringName, StringName] = {}


func _ready() -> void:
	if model_root == null:
		model_root = get_parent() as Node3D
	if skeleton == null and get_parent():
		var found := get_parent().find_children("*", "Skeleton3D", true, false)
		if not found.is_empty():
			skeleton = found[0] as Skeleton3D
	if skeleton == null:
		push_warning("CharacterOutfit: не найден Skeleton3D (%s)" % get_path())
		return
	if follow_session:
		Session.outfit_changed.connect(set_slot)
		apply_outfit(Session.outfit)


## Полностью заменяет наряд: слоты, которых нет в outfit, снимаются.
func apply_outfit(outfit: Dictionary) -> void:
	for s: StringName in _equipped.keys():
		if not outfit.has(s):
			set_slot(s, &"")
	for s: Variant in outfit:
		set_slot(StringName(str(s)), StringName(str(outfit[s])))


## Надевает item_id в слот (пустой item_id — снимает).
func set_slot(slot: StringName, item_id: StringName) -> void:
	if skeleton == null or _equipped.get(slot, &"") == item_id:
		return
	_clear_slot(slot)
	if item_id == &"":
		return
	var def: ItemDef = ItemCatalog.get_default().find(item_id)
	if def == null or def.scene == null:
		push_warning("CharacterOutfit: нет предмета «%s» в каталоге" % item_id)
		return
	var bone := skeleton.find_bone(def.bone)
	if bone < 0:
		push_warning("CharacterOutfit: у скелета нет кости %s (предмет %s)" % [def.bone, item_id])
		return
	var att := BoneAttachment3D.new()
	att.name = "Outfit_%s" % slot
	skeleton.add_child(att)
	att.bone_name = def.bone
	# промежуточный узел убирает масштаб скелета: смещения и размеры предмета
	# задаются в единицах модели, а не в единицах кости
	var holder := Node3D.new()
	holder.name = "Offset"
	holder.transform = Transform3D(Basis.from_scale(Vector3.ONE / _bone_scale(bone)),
		Vector3.ZERO) * def.get_offset()
	att.add_child(holder)
	holder.add_child(def.scene.instantiate())
	_attached[slot] = att
	_equipped[slot] = item_id


## Что сейчас надето: slot → item_id.
func get_outfit() -> Dictionary:
	return _equipped.duplicate()


func _clear_slot(slot: StringName) -> void:
	var att: BoneAttachment3D = _attached.get(slot)
	if att and is_instance_valid(att):
		att.get_parent().remove_child(att)
		att.queue_free()
	_attached.erase(slot)
	_equipped.erase(slot)


## Масштаб кости относительно model_root (у Armature он ×39.4).
func _bone_scale(bone: int) -> Vector3:
	var rel := skeleton.global_transform
	if model_root:
		rel = model_root.global_transform.affine_inverse() * rel
	var s := (rel * skeleton.get_bone_global_rest(bone)).basis.get_scale()
	return Vector3(maxf(s.x, 0.0001), maxf(s.y, 0.0001), maxf(s.z, 0.0001))
