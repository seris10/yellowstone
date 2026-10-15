shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap;

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D coverage_texture : filter_nearest, repeat_disable;
uniform sampler2D support_texture : filter_nearest, repeat_disable;
uniform vec2 mask_origin_m;
uniform vec2 mask_extent_m;
uniform float needle_repeat_m;
uniform float shoot_envelope_m;
uniform float lod_begin_m = 0.0;
uniform float lod_end_m = 350.0;
uniform bool lod_dither_invert = false;
uniform vec3 tint : source_color = vec3(0.86, 0.92, 0.82);
uniform vec3 base_color : source_color = vec3(0.12, 0.17, 0.08);
uniform float texture_color_detail = 0.12;
uniform bool cluster_mode = false;
uniform bool near_shoot_mode = false;
uniform int geometry_revision = 1;
uniform float skin_fade_begin_m = 180.0;
uniform float skin_fade_end_m = 260.0;
varying vec3 world;
varying vec3 world_normal;
varying float wood;
varying vec2 mask_world;
varying float masked_part;
varying float lod_distance;

void vertex() {
	wood = cluster_mode ? COLOR.g : 0.0;
	masked_part = !cluster_mode || wood < 0.5 || (near_shoot_mode && COLOR.b < 0.25) ? 1.0 : 0.0;
	float depth = length(MODEL_MATRIX[1].xyz);
	float crown_depth = min(depth, 2.0);
	lod_distance = distance(MODEL_MATRIX[3].xyz, CAMERA_POSITION_WORLD);
	if (geometry_revision >= 2 && wood > 0.5 && COLOR.b > 0.25) {
		vec3 root = INSTANCE_CUSTOM.xyz * vec3(1.0, depth, 1.0);
		float root_radius = INSTANCE_CUSTOM.w > 0.5 ? clamp(length(root.xz) * 0.03, 0.018, 0.065) : clamp(depth / 112.0, 0.025, 0.14);
		float joint_radius = min(root_radius, 0.045);
		vec3 start = COLOR.b > 0.75 ? vec3(0.0, -crown_depth * 1.05, 0.0) : vec3(0.0);
		vec3 end = COLOR.b > 0.75 ? root : vec3(0.0, -crown_depth * 1.05, 0.0);
		float start_radius = COLOR.b > 0.75 ? joint_radius : 0.006;
		float end_radius = COLOR.b > 0.75 ? root_radius : joint_radius;
		vec3 delta = end - start;
		float axis_length = max(length(delta), 0.00001);
		vec3 axis = length(delta) > 0.00001 ? delta / axis_length : vec3(0.0, -1.0, 0.0);
		vec3 across = normalize(cross(axis, abs(axis.y) < 0.9 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
		vec3 radial = across * cos(UV.y) + cross(axis, across) * sin(UV.y);
		VERTEX = (mix(start, end, UV.x) + radial * mix(start_radius, end_radius, UV.x)) / vec3(1.0, depth, 1.0);
		NORMAL = normalize((radial + axis * (start_radius - end_radius) / axis_length) * vec3(1.0, depth, 1.0));
	} else if (wood > 0.5 && COLOR.b > 0.75) {
		vec3 axis = vec3(INSTANCE_CUSTOM.x, INSTANCE_CUSTOM.y * depth + crown_depth * 1.05, INSTANCE_CUSTOM.z);
		vec3 across = normalize(cross(axis, abs(axis.y) < 0.9 * length(axis) ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0)));
		if (UV.y > 0.5) across = normalize(cross(axis, across));
		vec3 offset = across * (VERTEX.x + VERTEX.z);
		offset.y /= depth;
		VERTEX = mix(vec3(0.0, -crown_depth * 1.05 / depth, 0.0), INSTANCE_CUSTOM.xyz, UV.x) + offset;
		NORMAL = normalize(cross(axis, across)) * vec3(1.0, depth, 1.0);
	} else if (near_shoot_mode && (wood < 0.5 || COLOR.b < 0.25)) {
		float size_scale = min(1.0, crown_depth / shoot_envelope_m);
		float half_card = 0.5 * shoot_envelope_m * size_scale;
		float anchor = mix(half_card, crown_depth - half_card, COLOR.r);
		VERTEX.y = (-anchor + (VERTEX.y + COLOR.r) * size_scale) / depth;
		NORMAL = normalize(NORMAL * vec3(1.0, depth / size_scale, 1.0));
	} else if (wood > 0.5) {
		VERTEX.y *= crown_depth / depth;
	} else if (cluster_mode) {
		VERTEX.y *= crown_depth / depth;
	}
	world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	mask_world = near_shoot_mode && masked_part > 0.5 ? (MODEL_MATRIX * vec4(UV2.x, 0.0, UV2.y, 1.0)).xz : world.xz;
	world_normal = normalize(MODEL_NORMAL_MATRIX * NORMAL);
}

void fragment() {
	float camera_distance = distance(world, CAMERA_POSITION_WORLD);
	float skin_fade = smoothstep(skin_fade_begin_m, skin_fade_end_m, camera_distance);
	float threshold = fract(sin(dot(floor(FRAGCOORD.xy), vec2(12.9898, 78.233))) * 43758.5453);
	if (cluster_mode) {
		if (skin_fade > threshold) discard;
		float lod_visibility = 1.0 - smoothstep(lod_end_m - 8.0, lod_end_m, lod_distance);
		if (lod_begin_m > 0.0) lod_visibility *= smoothstep(lod_begin_m - 8.0, lod_begin_m, lod_distance);
		float lod_threshold = lod_dither_invert ? 1.0 - threshold : threshold;
		if (lod_threshold > lod_visibility) discard;
	} else if (skin_fade <= threshold) {
		discard;
	}
	vec2 coverage_uv = (mask_world - mask_origin_m) / mask_extent_m;
	float coverage = texture(coverage_texture, coverage_uv).r;
	float support = texture(support_texture, coverage_uv).r;
	if (masked_part > 0.5 && (coverage < 0.5 || support < 0.5 || any(lessThan(coverage_uv, vec2(0.0))) || any(greaterThan(coverage_uv, vec2(1.0))))) {
		discard;
	}
	vec3 weights = abs(world_normal);
	vec2 leaf_uv = world.xz / needle_repeat_m;
	if (weights.x > weights.y && weights.x > weights.z) {
		leaf_uv = world.zy / needle_repeat_m;
	} else if (weights.z > weights.y) {
		leaf_uv = world.xy / needle_repeat_m;
	}
	vec4 leaf = texture(albedo_texture, near_shoot_mode ? UV : fract(leaf_uv));
	if (!FRONT_FACING) NORMAL = -NORMAL;
	if (wood > 0.5) {
		ALBEDO = vec3(0.19, 0.14, 0.085);
	} else if (cluster_mode) {
		if (leaf.a < 0.32) discard;
		ALBEDO = mix(base_color, tint * leaf.rgb, 0.78);
	} else {
		ALBEDO = mix(base_color, tint * leaf.rgb, leaf.a * texture_color_detail);
	}
	ROUGHNESS = 0.86;
	BACKLIGHT = ALBEDO * 0.20;
}
