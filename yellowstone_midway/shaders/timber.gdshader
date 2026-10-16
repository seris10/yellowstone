shader_type spatial;
render_mode diffuse_burley;
#include "res://shaders/wood_grain.gdshaderinc"

// Grain runs along this object-space axis; box members carry their size in vertex positions.
uniform vec3 grain_axis = vec3(0.0, 1.0, 0.0);
uniform vec3 wood_light = vec3(0.50, 0.40, 0.30);
uniform vec3 wood_dark = vec3(0.27, 0.20, 0.15);
uniform float patina = 0.30;
varying vec3 local_pos;
varying vec3 world_pos;

void vertex() {
 local_pos = VERTEX;
 world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
 vec3 ax = normalize(grain_axis);
 float along = dot(local_pos, ax);
 vec3 perp = local_pos - ax * along;
 float across = perp.x * 0.8 + perp.y * 0.6 + perp.z * 0.7;
 float tone = wood_hash(floor(world_pos.xz * 0.5));
 float g = wood_grain(along + tone * 9.0, across, tone);
 float weather = patina + 0.25 * wood_fbm(world_pos.xz * 0.8 + world_pos.y);
 ALBEDO = wood_color(g, tone, weather, wood_light, wood_dark);
 ROUGHNESS = 0.80;
 SPECULAR = 0.25;
}
