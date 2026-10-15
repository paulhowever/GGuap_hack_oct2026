shader_type canvas_item;
// Процедурная виниловая пластинка на квадратном ColorRect.
// Бороздки, неподвижный блик, вращающаяся «яблоко»-наклейка с меткой.

uniform vec4 disc_color : source_color = vec4(0.09, 0.075, 0.10, 1.0);
uniform vec4 groove_color : source_color = vec4(0.16, 0.14, 0.18, 1.0);
uniform vec4 rim_color : source_color = vec4(0.30, 0.26, 0.32, 1.0);
uniform vec4 label_color : source_color = vec4(1.0, 0.478, 0.239, 1.0);
uniform vec4 label_color_2 : source_color = vec4(0.953, 0.902, 0.827, 1.0);
uniform vec4 sheen_color : source_color = vec4(1.0, 0.85, 0.7, 1.0);

uniform float spin_speed = 0.35;          // оборотов в секунду
uniform float label_radius : hint_range(0.1, 0.6) = 0.36;
uniform float sheen_strength : hint_range(0.0, 1.0) = 0.35;
uniform float pulse : hint_range(0.0, 1.0) = 0.0;

void fragment() {
	vec2 p = UV * 2.0 - 1.0;
	float r = length(p);
	float aa = fwidth(r) * 1.5;
	float disc_mask = 1.0 - smoothstep(1.0 - aa, 1.0, r);

	float ang_static = atan(p.y, p.x);
	float ang = ang_static + TIME * spin_speed * TAU;

	// Бороздки
	float grooves = 0.5 + 0.5 * sin(r * 260.0);
	float track_gaps = smoothstep(0.0, 0.01, abs(fract(r * 6.0) - 0.5) - 0.47);
	vec3 col = mix(disc_color.rgb, groove_color.rgb, grooves * 0.35 + track_gaps * 0.4);

	// Неподвижный блик (свет не вращается вместе с диском)
	float sheen = pow(abs(cos(ang_static - 0.75)), 18.0) * smoothstep(label_radius, label_radius + 0.08, r);
	col += sheen_color.rgb * sheen * sheen_strength * (0.8 + pulse * 0.6);

	// Ободок
	float rim = smoothstep(0.94, 0.985, r);
	col = mix(col, rim_color.rgb, rim * 0.6);

	// Наклейка
	float lr = label_radius * (1.0 + pulse * 0.05);
	float label_mask = 1.0 - smoothstep(lr - aa, lr, r);
	vec3 lcol = label_color.rgb * (1.0 + pulse * 0.25);
	float ring = smoothstep(0.012, 0.0, abs(r - lr * 0.72));
	lcol = mix(lcol, label_color_2.rgb, ring * 0.9);
	// вращающаяся метка, чтобы было видно вращение
	vec2 rp = vec2(cos(ang), sin(ang)) * r;
	float mark = smoothstep(0.05, 0.035, length(rp - vec2(lr * 0.48, 0.0)));
	lcol = mix(lcol, label_color_2.rgb, mark);
	float stripe = smoothstep(0.02, 0.0, abs(rp.y)) * step(0.0, -rp.x) * step(r, lr * 0.6) * step(0.06, r);
	lcol = mix(lcol, label_color_2.rgb, stripe * 0.6);
	col = mix(col, lcol, label_mask);

	// Отверстие
	float hole = 1.0 - smoothstep(0.03 - aa, 0.03, r);
	col = mix(col, disc_color.rgb * 0.5, hole);

	COLOR = vec4(col, disc_mask);
}
