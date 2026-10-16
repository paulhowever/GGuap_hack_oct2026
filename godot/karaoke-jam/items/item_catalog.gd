class_name ItemCatalog
extends Resource
## Каталог предметов гардероба. Порядок items — порядок кнопок в гардеробе.
## Игроку никак не показывается: это просто данные, чтобы предметы не хардкодились.

const DEFAULT_PATH := "res://items/catalog.tres"

@export var items: Array[ItemDef] = []

static var _default: ItemCatalog


## Общий каталог проекта (res://items/catalog.tres), загружается один раз.
static func get_default() -> ItemCatalog:
	if _default == null:
		_default = load(DEFAULT_PATH) as ItemCatalog
		if _default == null:
			push_error("ItemCatalog: не удалось загрузить %s" % DEFAULT_PATH)
			_default = ItemCatalog.new()
	return _default


func find(item_id: StringName) -> ItemDef:
	for it: ItemDef in items:
		if it and it.id == item_id:
			return it
	return null
