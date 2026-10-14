shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap;

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D coverage_texture : filter_nearest, repeat_disable;
uniform sampler2D support_texture : filter_nearest, repeat_disable;
uniform vec2 mask_origin_m;
uniform vec2 mask_extent_m;
uniform float needle_repeat_m;
uniform vec3 tint : source_color = vec3(0.86, 0.92, 0.82);
uniform vec3 base_color : source_color = vec3(0.12, 0.17, 0.08);
uniform float texture_color_detail = 0.12;
uniform bool cluster_mode = false;
uniform bool near_shoot_mode = false;
uniform float skin_fade_begin_m = 180.0;
uniform float skin_fade_end_m = 260.0;
varying vec3 world;
varying vec3 world_normal;

void vertex() {
	if (near_shoot_mode) {
		float depth = length(MODEL_MATRIX[1].xyz);
		float size_scale = min(1.0, depth / 0.40);
		float half_card = 0.20 * size_scale;
		float anchor = mix(half_card, depth - half_card, COLOR.r);
		VERTEX.y = (-anchor + (VERTEX.y + COLOR.r) * size_scale) / depth;
	}
	world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	world_normal = normalize(mat3(MODEL_MATRIX) * NORMAL);
}

void fragment() {
	vec2 coverage_uv = (world.xz - mask_origin_m) / mask_extent_m;
	float coverage = texture(coverage_texture, coverage_uv).r;
	float support = texture(support_texture, coverage_uv).r;
	if (coverage < 0.5 || support < 0.5 || any(lessThan(coverage_uv, vec2(0.0))) || any(greaterThan(coverage_uv, vec2(1.0)))) {
		discard;
	}
	vec3 weights = abs(world_normal);
	vec2 leaf_uv = world.xz / needle_repeat_m;
	if (weights.x > weights.y && weights.x > weights.z) {
		leaf_uv = world.zy / needle_repeat_m;
	} else if (weights.z > weights.y) {
		leaf_uv = world.xy / needle_repeat_m;
	}
	vec4 leaf = texture(albedo_texture, near_shoot_mode ? UV : leaf_uv);
	float camera_distance = distance(world, CAMERA_POSITION_WORLD);
	float skin_fade = smoothstep(skin_fade_begin_m, skin_fade_end_m, camera_distance);
	float threshold = fract(sin(dot(floor(FRAGCOORD.xy), vec2(12.9898, 78.233))) * 43758.5453);
	if (cluster_mode) {
		if (skin_fade > threshold) discard;
	} else if (skin_fade <= threshold) {
		discard;
	}
	if (!FRONT_FACING) NORMAL = -NORMAL;
	if (cluster_mode) {
		if (leaf.a < 0.32) discard;
		ALBEDO = mix(base_color, tint * leaf.rgb, 0.30);
	} else {
		ALBEDO = mix(base_color, tint * leaf.rgb, leaf.a * texture_color_detail);
	}
	ROUGHNESS = 0.86;
	BACKLIGHT = ALBEDO * 0.20;
}
