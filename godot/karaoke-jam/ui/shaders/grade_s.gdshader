shader_type canvas_item;
// Статичный вертикальный градиент для текста ранга S (без анимации).
// Альфа берётся из глифа (Label с font_color = белый).
// grad_top/grad_bottom — верх и низ буквы в локальных пикселях Label;
// задаются из скрипта (UV у текста — атлас шрифта, для градиента не годится).

uniform vec4 top_color : source_color = vec4(0.07, 0.82, 0.78, 1.0); // бирюзовый
uniform vec4 bottom_color : source_color = vec4(1.0, 0.96, 0.44, 1.0); // светлое золото
uniform float grad_top = 0.0;
uniform float grad_bottom = 100.0;

varying float local_y;

void vertex() {
	local_y = VERTEX.y;
}

void fragment() {
	float t = clamp((local_y - grad_top) / max(grad_bottom - grad_top, 1.0), 0.0, 1.0);
	COLOR.rgb = mix(top_color.rgb, bottom_color.rgb, t);
}
