shader_type spatial;
render_mode diffuse_burley;
#include "res://shaders/ground_surface.gdshaderinc"

uniform float core_cut_x_min_m = 0.0;
uniform float core_cut_x_max_m = 0.0;
uniform float core_cut_z_min_m = 0.0;
uniform float core_cut_z_max_m = 0.0;
uniform float core_cut_active = 0.0;
varying vec3 world;
varying vec3 world_normal;

void vertex() {
 world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
 world_normal = normalize(MODEL_NORMAL_MATRIX * NORMAL);
 TANGENT = ground_tangent(normalize(NORMAL));
 BINORMAL = normalize(cross(TANGENT, NORMAL));
}

void fragment() {
 if (core_cut_active > 0.5 && world.x >= core_cut_x_min_m && world.x <= core_cut_x_max_m && world.z >= core_cut_z_min_m && world.z <= core_cut_z_max_m) {
  discard;
 }
 GroundSurface surface = ground_surface(world, normalize(world_normal), INV_VIEW_MATRIX[3].xyz);
 ALBEDO = surface.albedo;
 NORMAL_MAP = vec3(surface.normal_xy * 0.5 + 0.5, 1.0);
 NORMAL_MAP_DEPTH = 1.0;
 ROUGHNESS = surface.roughness;
 AO = surface.occlusion;
 SPECULAR = surface.specular;
}
