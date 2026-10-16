extends Node
## Глобальное состояние игрока: ник, задержка, сложность, первый запуск, настройки.
## Всё хранится в user://settings.cfg (в вебе — IndexedDB браузера).
## Изменения сложности/громкости/задержки VoiceBridge пересылает в JS (voice.configure).

signal nickname_changed(nickname: String)
## Изменился текст «О себе» (показывается в окне кавера у других игроков).
signal bio_changed(bio: String)
signal lag_changed(lag_ms: int)
signal headphones_changed(confirmed: bool)
signal music_volume_changed(value: float)
signal difficulty_changed(difficulty: String)
## Изменился наряд персонажа (slot → item_id; пустой item_id — слот снят).
signal outfit_changed(slot: StringName, item_id: StringName)

const SAVE_PATH := "user://settings.cfg"
const LAST_RESULT_PATH := "user://last_result.json"
const DEFAULT_NICKNAME := "Гость"
const NICKNAME_MAX := 24
## Лимит «О себе» (как BIO_MAX_LENGTH на бэкенде).
const BIO_MAX := 200
const LAG_MIN_MS := -100
const LAG_MAX_MS := 500
const DIFFICULTIES: Array[String] = ["easy", "normal", "hard"]
const DEFAULT_DIFFICULTY := "normal"

var nickname: String = DEFAULT_NICKNAME:
	set(value):
		value = value.strip_edges().left(NICKNAME_MAX)
		if value.is_empty():
			value = DEFAULT_NICKNAME
		if value == nickname:
			return
		nickname = value
		nickname_changed.emit(nickname)

## «О себе»: до BIO_MAX символов, переносы строк сохраняются, пробелы по краям обрезаются.
var bio: String = "":
	set(value):
		value = value.strip_edges().left(BIO_MAX).strip_edges()
		if value == bio:
			return
		bio = value
		bio_changed.emit(bio)

## Суммарная задержка «звук услышан → голос в микрофоне», мс.
var lag_ms: int = 120:
	set(value):
		value = clampi(value, LAG_MIN_MS, LAG_MAX_MS)
		if value == lag_ms:
			return
		lag_ms = value
		lag_changed.emit(lag_ms)

var is_calibrated: bool = false
## Игрок подстраивал задержку вручную (±10 мс) — значение надо передать в JS.
var lag_manual: bool = false
var first_run_done: bool = false

## Игрок подтвердил, что поёт в проводных наушниках (автоопределение невозможно).
var headphones_confirmed: bool = false:
	set(value):
		if value == headphones_confirmed:
			return
		headphones_confirmed = value
		headphones_changed.emit(headphones_confirmed)

## Громкость фоновой музыки меню при каждом запуске игры (из сохранения не читается).
const DEFAULT_MUSIC_VOLUME := 0.1

## Громкость фоновой музыки меню 0..1 (линейная), применяется только к шине Music.
## Минус песни и прослушивание каверов в JS от неё не зависят.
var music_volume: float = DEFAULT_MUSIC_VOLUME:
	set(value):
		music_volume = clampf(value, 0.0, 1.0)
		_apply_music_volume()
		music_volume_changed.emit(music_volume)

## Сложность: допуск по высоте (easy 200 / normal 120 / hard 60 центов).
var difficulty: String = DEFAULT_DIFFICULTY:
	set(value):
		if not value in DIFFICULTIES:
			value = DEFAULT_DIFFICULTY
		if value == difficulty:
			return
		difficulty = value
		difficulty_changed.emit(difficulty)

## Наряд персонажа из гардероба: slot (StringName) → item_id (StringName).
## На модель надевает CharacterOutfit (res://items/character_outfit.gd).
var outfit: Dictionary[StringName, StringName] = {}

# --- Состояние текущей попытки (не сохраняется) -----------------------------

## Выбранная песня (id из GET /api/v1/songs).
var song_id: String = ""
## Краткая информация о выбранной песне (элемент списка /songs).
var song_info: Dictionary = {}
## Челлендж (на бэкенде пока не реализован) — пустая строка = нет.
var challenge_id: String = ""
## Последний результат on_result (контракт TakeResult).
var last_result: Dictionary = {}
## Экран результата открыт кнопкой «Мой последний результат» (просмотр, а не сразу после пения).
var result_review: bool = false

## Мой последний результат, переживает перезапуск (user://last_result.json).
## {result: TakeResult, song_info: элемент /songs}. Пусто — ещё ни разу не пел.
var saved_result: Dictionary = {}


func _ready() -> void:
	load_settings()
	_load_saved_result()


## Результат только что спетого дубля: показываем и сохраняем на диск как «последний».
func set_last_result(result: Dictionary) -> void:
	last_result = result
	result_review = false
	saved_result = {"result": result, "song_info": song_info}
	var f := FileAccess.open(LAST_RESULT_PATH, FileAccess.WRITE)
	if f == null:
		push_warning("Session: не удалось сохранить результат (%s)" % error_string(FileAccess.get_open_error()))
		return
	f.store_string(JSON.stringify(saved_result))


func has_saved_result() -> bool:
	return saved_result.get("result") is Dictionary and not (saved_result.result as Dictionary).is_empty()


## Открыть сохранённый результат на экране результата (режим просмотра).
func open_saved_result() -> bool:
	if not has_saved_result():
		return false
	last_result = saved_result.result
	result_review = true
	var info = saved_result.get("song_info")
	song_info = info if info is Dictionary else {}
	song_id = str(last_result.get("song_id", song_info.get("id", "")))
	return true


func _load_saved_result() -> void:
	if not FileAccess.file_exists(LAST_RESULT_PATH):
		return
	var data = JSON.parse_string(FileAccess.get_file_as_string(LAST_RESULT_PATH))
	saved_result = data if data is Dictionary else {}


func is_first_run() -> bool:
	return not first_run_done


func mark_first_run_done() -> void:
	first_run_done = true
	save_settings()


func set_calibrated_lag(value_ms: int) -> void:
	lag_ms = value_ms
	is_calibrated = true
	lag_manual = false
	save_settings()


## Ручная подстройка задержки (кнопки ±10 мс).
func nudge_lag(delta_ms: int) -> void:
	lag_manual = true
	lag_ms += delta_ms
	save_settings()


## Надеть предмет в слот (пустой item_id — снять). Сохраняет настройки.
func equip_item(slot: StringName, item_id: StringName) -> void:
	if outfit.get(slot, &"") == item_id:
		return
	if item_id == &"":
		outfit.erase(slot)
	else:
		outfit[slot] = item_id
	outfit_changed.emit(slot, item_id)
	save_settings()


func get_equipped(slot: StringName) -> StringName:
	return outfit.get(slot, &"")


## Аватар для профиля на бэкенде (POST /players): {outfit: {slot: item_id}}.
func get_avatar() -> Dictionary:
	var o := {}
	for s: StringName in outfit:
		o[String(s)] = String(outfit[s])
	return {"outfit": o}


func load_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SAVE_PATH) == OK:
		nickname = cfg.get_value("player", "nickname", DEFAULT_NICKNAME)
		bio = str(cfg.get_value("player", "bio", ""))
		lag_ms = cfg.get_value("audio", "lag_ms", lag_ms)
		is_calibrated = cfg.get_value("audio", "is_calibrated", false)
		lag_manual = cfg.get_value("audio", "lag_manual", false)
		headphones_confirmed = cfg.get_value("audio", "headphones_confirmed", false)
		difficulty = cfg.get_value("game", "difficulty", DEFAULT_DIFFICULTY)
		first_run_done = cfg.get_value("app", "first_run_done", false)
		outfit.clear()
		var saved: Variant = cfg.get_value("character", "outfit", {})
		if saved is Dictionary:
			for k: Variant in saved:
				outfit[StringName(str(k))] = StringName(str(saved[k]))
	_apply_music_volume()


func save_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.set_value("player", "nickname", nickname)
	cfg.set_value("player", "bio", bio)
	cfg.set_value("audio", "lag_ms", lag_ms)
	cfg.set_value("audio", "is_calibrated", is_calibrated)
	cfg.set_value("audio", "lag_manual", lag_manual)
	cfg.set_value("audio", "headphones_confirmed", headphones_confirmed)
	cfg.set_value("audio", "music_volume", music_volume)
	cfg.set_value("game", "difficulty", difficulty)
	cfg.set_value("app", "first_run_done", first_run_done)
	cfg.set_value("character", "outfit", outfit)
	var err := cfg.save(SAVE_PATH)
	if err != OK:
		push_warning("Session: не удалось сохранить настройки (%s)" % error_string(err))


## Сброс к «первому запуску» — удобно для отладки.
func reset_settings() -> void:
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SAVE_PATH))
	DirAccess.remove_absolute(ProjectSettings.globalize_path(LAST_RESULT_PATH))
	saved_result = {}
	first_run_done = false
	is_calibrated = false
	lag_manual = false


func _apply_music_volume() -> void:
	var idx := AudioServer.get_bus_index(&"Music")
	if idx >= 0:
		AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(music_volume, 0.0001)))
