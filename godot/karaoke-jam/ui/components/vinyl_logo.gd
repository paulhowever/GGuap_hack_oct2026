extends Control
## Логотип: винил + свечение + название. Ритм-эффекты на детях через BeatReactor.
## Здесь только интро-анимация и «вздрагивание» на смену такта.

@export var title_text: String = "KaraokeJam":
	set(v):
		title_text = v
		if is_node_ready():
			%Title.text = v
@export var subtitle_text: String = "пой в ритм":
	set(v):
		subtitle_text = v
		if is_node_ready():
			%Subtitle.text = v

@onready var _disc: Control = %Disc
@onready var _title: Label = %Title


func _ready() -> void:
	%Title.text = title_text
	%Subtitle.text = subtitle_text


## Появление: диск «выкатывается», заголовок падает сверху.
func play_intro(delay: float = 0.0) -> void:
	modulate.a = 0.0
	_disc.pivot_offset = _disc.size * 0.5
	_disc.scale = Vector2(0.6, 0.6)
	_disc.rotation = -1.2
	var tw := create_tween().set_parallel()
	tw.tween_property(self, "modulate:a", 1.0, 0.4).set_delay(delay)
	tw.tween_property(_disc, "scale", Vector2.ONE, 0.9).set_delay(delay) \
		.set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(_disc, "rotation", 0.0, 0.9).set_delay(delay) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	# Заголовок внутри контейнера — анимируем прозрачность, не позицию.
	_title.modulate.a = 0.0
	tw.tween_property(_title, "modulate:a", 1.0, 0.5).set_delay(delay + 0.25)
