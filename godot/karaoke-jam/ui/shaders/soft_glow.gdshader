shader_type canvas_item;
render_mode blend_add;
// Имитация свечения без HDR/glow: аддитивное радиальное пятно на ColorRect.
// Сила управляется intensity (BeatReactor может дергать её в ритм).

uniform vec4 glow_color : source_color = vec4(1.0, 0.478, 0.239, 1.0);
uniform float intensity : hint_range(0.0, 2.0) = 0.45;
uniform float falloff : hint_range(0.5, 8.0) = 2.4;
uniform float inner_radius : hint_range(0.0, 0.95) = 0.0;

void fragment() {
	float d = length(UV - 0.5) * 2.0;
	float t = clamp((d - inner_radius) / max(1.0 - inner_radius, 0.001), 0.0, 1.0);
	float a = pow(1.0 - t, falloff) * step(d, 1.0);
	COLOR = vec4(glow_color.rgb * a * intensity * glow_color.a, 1.0);
}
