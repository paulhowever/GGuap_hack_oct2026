shader_type canvas_item;
// Фон «уютная студия»: тёплый градиент, акустические панели-пирамидки,
// тёплый свет лампы (дышит в ритм), мягкие звуковые волны, виньетка, зерно.
// Ритм подаётся извне через beat_pulse / measure_pulse (BeatReactor).

uniform vec4 color_top : source_color = vec4(0.169, 0.141, 0.188, 1.0);
uniform vec4 color_bottom : source_color = vec4(0.118, 0.102, 0.141, 1.0);
uniform vec4 light_color : source_color = vec4(1.0, 0.70, 0.42, 1.0);
uniform vec4 wave_color : source_color = vec4(1.0, 0.478, 0.239, 1.0);
uniform vec4 wave_color_2 : source_color = vec4(0.373, 0.827, 0.737, 1.0);

uniform vec2 light_pos = vec2(0.36, 0.45);
uniform float light_radius : hint_range(0.05, 1.5) = 0.55;
uniform float light_strength : hint_range(0.0, 1.0) = 0.22;
uniform float panel_tiles : hint_range(2.0, 40.0) = 11.0;
uniform float panel_strength : hint_range(0.0, 1.0) = 0.35;
uniform float wave_y : hint_range(0.0, 1.0) = 0.80;
uniform float wave_strength : hint_range(0.0, 1.0) = 0.35;
uniform float vignette : hint_range(0.0, 2.0) = 0.9;
uniform float grain : hint_range(0.0, 0.2) = 0.035;

uniform float beat_pulse : hint_range(0.0, 1.0) = 0.0;
uniform float measure_pulse : hint_range(0.0, 1.0) = 0.0;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void fragment() {
	vec2 uv = UV;
	float aspect = SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x;
	vec2 p = vec2(uv.x * aspect, uv.y);

	vec3 col = mix(color_top.rgb, color_bottom.rgb, smoothstep(0.0, 1.0, uv.y));

	// Акустические панели: пирамидки с гранями разной яркости
	vec2 cell = fract(p * panel_tiles) - 0.5;
	float facet;
	if (abs(cell.x) > abs(cell.y)) {
		facet = cell.x > 0.0 ? -0.6 : 0.4;
	} else {
		facet = cell.y > 0.0 ? -1.0 : 1.0;
	}
	float seam = smoothstep(0.47, 0.5, max(abs(cell.x), abs(cell.y)));
	col += (facet * 0.018 - seam * 0.03) * panel_strength;

	// Тёплый свет лампы
	vec2 lp = vec2(light_pos.x * aspect, light_pos.y);
	float d = length(p - lp);
	float radius = light_radius * (1.0 + beat_pulse * 0.06 + measure_pulse * 0.08);
	float glow = exp(-pow(d / radius, 2.0) * 2.2);
	col += light_color.rgb * glow * light_strength * (0.85 + beat_pulse * 0.35);

	// Мягкие звуковые волны
	float waves = 0.0;
	vec3 wcol = vec3(0.0);
	for (int i = 0; i < 3; i++) {
		float fi = float(i);
		float amp = (0.018 + fi * 0.008) * (1.0 + beat_pulse * 1.2);
		float y = wave_y + fi * 0.035
			+ amp * sin(p.x * (2.2 + fi * 0.9) + TIME * (0.5 + fi * 0.25) + fi * 1.7)
			+ amp * 0.5 * sin(p.x * 7.0 - TIME * 0.8 + fi);
		float line = smoothstep(0.004, 0.0, abs(uv.y - y)) * (0.9 - fi * 0.25);
		float haze = exp(-abs(uv.y - y) * 40.0) * 0.25;
		vec3 c = mix(wave_color.rgb, wave_color_2.rgb, fi / 2.0);
		wcol += c * (line + haze);
	}
	col += wcol * wave_strength;

	// Виньетка
	vec2 vc = uv - 0.5;
	vc.x *= aspect * 0.75;
	col *= 1.0 - dot(vc, vc) * vignette;

	// Плёночное зерно
	col += (hash(uv * 900.0 + fract(TIME * 7.0)) - 0.5) * grain;

	COLOR = vec4(col, 1.0);
}
