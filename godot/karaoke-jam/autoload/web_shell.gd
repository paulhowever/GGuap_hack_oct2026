extends Node
## Связь с HTML-оболочкой (shell.html). Не аудио — только ник и мелочи страницы.
## Ожидаемый контракт со стороны HTML (делает фронтенд):
##   <input id="kj-nickname">            — поле ника на оверлее «Нажми, чтобы начать»
##   window.kjGetNickname() -> string    — (опционально) вернуть ник
##   window.kjSetNickname(nick)          — (опционально) запомнить ник, сменённый в игре
##   window.kjOnNicknameChanged = fn     — (опционально) Godot подпишется на смену ника
## Оверлей — только первый ввод ника; дальше ник меняется в гардеробе, и новое значение
## уходит обратно на страницу (иначе при следующем запуске оверлей вернул бы старый ник).
## Вне веба (редактор/десктоп) работает как заглушка: ник берётся из Session.

signal nickname_received(nickname: String)


const INPUT_ID := "kj-nickname"

var _js_callback: JavaScriptObject   # держим ссылку, иначе GC уберёт колбэк


func _ready() -> void:
	if not is_web():
		return
	_subscribe_nickname_changes()
	Session.nickname_changed.connect(push_nickname)


func is_web() -> bool:
	return OS.has_feature("web")


## Прочитать ник со страницы. Возвращает "" если его нет / не веб.
func read_nickname() -> String:
	if not is_web():
		return ""
	var js := """
		(function(){
			if (typeof window.kjGetNickname === 'function') return String(window.kjGetNickname() || '');
			var el = document.getElementById('%s');
			return el ? String(el.value || '') : '';
		})()
	""" % INPUT_ID
	var value = JavaScriptBridge.eval(js, true)
	return String(value) if value != null else ""


## Подтянуть ник со страницы в Session (если он там есть).
func sync_nickname_to_session() -> void:
	var nick := read_nickname()
	if not nick.strip_edges().is_empty():
		Session.nickname = nick
		Session.save_settings()
		nickname_received.emit(Session.nickname)


## Записать ник на страницу (поле оверлея и localStorage). Без kjSetNickname — только поле.
func push_nickname(nick: String) -> void:
	if not is_web():
		return
	var js := """
		(function(v){
			if (typeof window.kjSetNickname === 'function') { window.kjSetNickname(v); return; }
			var el = document.getElementById('%s');
			if (el) el.value = v;
		})(%s)
	""" % [INPUT_ID, JSON.stringify(nick)]
	JavaScriptBridge.eval(js, true)


## Попросить страницу показать поле ника снова (для смены ника из настроек).
## Если страница этого не умеет — вернёт false, и UI использует поле ввода Godot.
func request_nickname_edit() -> bool:
	if not is_web():
		return false
	var ok = JavaScriptBridge.eval(
		"(typeof window.kjEditNickname === 'function') ? (window.kjEditNickname(), true) : false", true)
	return ok == true


func _subscribe_nickname_changes() -> void:
	_js_callback = JavaScriptBridge.create_callback(_on_js_nickname)
	var window := JavaScriptBridge.get_interface("window")
	if window:
		window.kjOnNicknameChanged = _js_callback


func _on_js_nickname(args: Array) -> void:
	if args.is_empty():
		return
	Session.nickname = String(args[0])
	Session.save_settings()
	nickname_received.emit(Session.nickname)
