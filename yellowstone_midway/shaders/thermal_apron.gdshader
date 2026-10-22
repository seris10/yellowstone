shader_type spatial;
render_mode cull_back, diffuse_burley;
#include "res://shaders/ground_surface.gdshaderinc"

uniform sampler2DArray pigment_layers : source_color, filter_linear_mipmap, repeat_disable;
uniform float mat_pigment_blend = 1.0;
uniform float pigment_available = 0.0;
uniform vec2 normal_grid_size = vec2(1.0);
uniform vec2 outflow_source_size = vec2(1.0);
uniform float normal_map_available = 0.0;
uniform float residual_normal_fade_near_m = 100.0;
uniform float residual_normal_fade_far_m = 220.0;
uniform sampler2DArray outflow_layers : filter_linear, repeat_disable;
uniform float wet_mask_available = 0.0;
uniform float flow_fraction_available = 0.0;
uniform float in_pool_available = 0.0;
uniform float extent_x_min_m = 0.0;
uniform float extent_z_min_m = 0.0;
uniform float extent_width_m = 1.0;
uniform float extent_height_m = 1.0;
uniform float pigment_x_min_m = -640.0;
uniform float pigment_z_min_m = -640.0;
uniform float pigment_width_m = 1280.0;
uniform float pigment_height_m = 1280.0;
uniform float outflow_x_min_m = -640.0;
uniform float outflow_z_min_m = -640.0;
uniform float outflow_width_m = 1280.0;
uniform float outflow_height_m = 1280.0;
uniform float flow_fraction_scale = 25.0;
uniform sampler2D spring_apron_display : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D spring_terrace_detail : filter_linear_mipmap_anisotropic, repeat_disable;
uniform float spring_display_mix = 1.0;
varying vec3 world;
varying vec3 world_normal;

void vertex() {
 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
 world_normal = normalize(MODEL_NORMAL_MATRIX * NORMAL);
 TANGENT = ground_tangent(normalize(NORMAL));
 BINORMAL = normalize(cross(TANGENT, NORMAL));
}

float outflow_sample(vec2 uv, float layer) {
 uv = (uv * outflow_source_size + vec2(1.0)) / vec2(textureSize(outflow_layers, 0).xy);
 return texture(outflow_layers, vec3(uv, layer)).r;
}

void fragment() {
 GroundSurface surface = ground_surface(world, normalize(world_normal), INV_VIEW_MATRIX[3].xyz);
 vec2 flow_uv = (world.xz - vec2(outflow_x_min_m, outflow_z_min_m)) / vec2(outflow_width_m, outflow_height_m);
 float wet = wet_mask_available > 0.5 ? outflow_sample(flow_uv, 0.0) : 0.0;
 float flow = flow_fraction_available > 0.5 ? clamp(outflow_sample(flow_uv, 1.0) * flow_fraction_scale, 0.0, 1.0) : 0.0;
 float pool = in_pool_available > 0.5 ? outflow_sample(flow_uv, 2.0) : 0.0;
 vec2 edge_position = world.xz - vec2(extent_x_min_m, extent_z_min_m);
 vec2 edge_distance = min(edge_position, vec2(extent_width_m, extent_height_m) - edge_position);
 float edge_blend = smoothstep(0.0, 8.0, min(edge_distance.x, edge_distance.y));
 float thermal = clamp(max(surface.mineral, max(wet, pool)), 0.0, 1.0) * (1.0 - surface.tread) * (1.0 - surface.snow) * edge_blend;
 vec3 base = surface.albedo;
 if (pigment_available > 0.5) {
  vec2 pigment_uv = (world.xz - vec2(pigment_x_min_m, pigment_z_min_m)) / vec2(pigment_width_m, pigment_height_m);
  vec4 pigment = mix(texture(pigment_layers, vec3(pigment_uv, 0.0)), texture(pigment_layers, vec3(pigment_uv, 1.0)), clamp(mat_pigment_blend, 0.0, 1.0));
  base = mix(base, pigment.rgb * surface.spatial_detail * surface.mineral_grain, pigment.a * thermal);
 }
 vec2 spring_uv = (world.xz - vec2(detail_x_min_m, detail_z_min_m)) / vec2(detail_width_m, detail_height_m);
 vec4 spring_color = texture(spring_apron_display, spring_uv);
 vec4 terrace = texture(spring_terrace_detail, spring_uv);
 float spring_support = spring_display_mix * thermal;
 vec3 display_color = spring_color.rgb * mix(vec3(1.0), surface.spatial_detail, 0.35) * surface.mineral_grain;
 base = mix(base, display_color, spring_color.a * spring_support);
 float mapped_contrast = abs(dot(surface.spatial_detail, vec3(0.2126, 0.7152, 0.0722)) - 1.0);
 float terrace_structure = max(smoothstep(0.06, 0.24, mapped_contrast), flow);
 float terrace_edge = terrace.b * terrace.a * spring_support * terrace_structure;
 base *= 1.0 - terrace_edge * 0.075;
 float wet_amount = clamp(max(wet, flow), 0.0, 1.0) * thermal;
 float film_amount = clamp(max(flow, pool), 0.0, 1.0) * thermal;
 base *= 1.0 - 0.18 * wet_amount * (1.0 - pool);
 ALBEDO = mix(base, base * 0.55, pool * 0.5 * thermal);
 vec2 detail_xy = surface.normal_xy;
 detail_xy += (terrace.rg * 2.0 - 1.0) * terrace.a * spring_support;
 float residual_fade = 1.0 - smoothstep(residual_normal_fade_near_m, residual_normal_fade_far_m, distance(world, INV_VIEW_MATRIX[3].xyz));
 if (normal_map_available > 0.5 && residual_fade > 0.0) {
  vec2 extent_uv = (world.xz - vec2(extent_x_min_m, extent_z_min_m)) / vec2(extent_width_m, extent_height_m);
  vec2 size = vec2(textureSize(outflow_layers, 0).xy);
  vec2 normal_uv = (extent_uv * (normal_grid_size - vec2(1.0)) + vec2(1.5)) / size;
  detail_xy += (vec2(texture(outflow_layers, vec3(normal_uv, 3.0)).r, texture(outflow_layers, vec3(normal_uv, 4.0)).r) * 2.0 - 1.0) * residual_fade;
 }
 float normal_length = length(detail_xy);
 if (normal_length > 0.99) {
  detail_xy *= 0.99 / normal_length;
 }
 NORMAL_MAP = vec3(detail_xy * 0.5 + 0.5, 1.0);
 NORMAL_MAP_DEPTH = 1.0;
 ROUGHNESS = mix(surface.roughness, 0.18, film_amount);
 AO = surface.occlusion;
 SPECULAR = mix(surface.specular, 0.55, film_amount);
}
