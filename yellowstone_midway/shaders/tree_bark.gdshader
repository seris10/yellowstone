shader_type spatial;
render_mode cull_disabled;
#include "res://shaders/tree_lod.gdshaderinc"

uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform vec4 bark_color : source_color = vec4(0.72, 0.72, 0.65, 1.0);
uniform float bark_roughness = 0.92;

void vertex() {
    tree_distance_m = distance(INSTANCE_CUSTOM.xyz, MAIN_CAM_INV_VIEW_MATRIX[3].xyz);
    POSITION = tree_lod_outside(tree_distance_m) ? vec4(2.0, 2.0, 2.0, 1.0) : PROJECTION_MATRIX * MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
}

void fragment() {
    if (tree_lod_discard(FRAGCOORD.xy)) discard;
    if (!FRONT_FACING) NORMAL = -NORMAL;
    ALBEDO = texture(albedo_texture, UV).rgb * bark_color.rgb * COLOR.rgb;
    ROUGHNESS = bark_roughness;
}
