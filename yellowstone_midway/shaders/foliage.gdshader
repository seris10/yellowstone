shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap, world_vertex_coords;
#include "res://shaders/tree_lod.gdshaderinc"
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform bool use_texture = false;
uniform float alpha_cutoff = 0.40;
uniform vec3 tint : source_color = vec3(0.96,1.00,0.90);
uniform float wind_strength = 0.2;
uniform vec2 wind_vector=vec2(1.8,0.6);
varying vec3 world;
void vertex(){
 world=VERTEX;
 float local_height=(VERTEX.y-MODEL_MATRIX[3].y)/max(length(MODEL_MATRIX[1].xyz),0.0001);
 float weight=clamp(local_height/(wind_strength<0.1?0.8:7.0),0.0,1.0);
 float bend=sin(TIME*1.7+world.x*0.2+world.z*0.15)*wind_strength*weight*weight;
 // Bend foliage in world coordinates.
 VERTEX+=vec3(bend*wind_vector.x,0.0,bend*wind_vector.y);
 tree_distance_m=distance(INSTANCE_CUSTOM.xyz,MAIN_CAM_INV_VIEW_MATRIX[3].xyz);
 POSITION=tree_lod_outside(tree_distance_m)?vec4(2.0,2.0,2.0,1.0):PROJECTION_MATRIX*VIEW_MATRIX*vec4(VERTEX,1.0);
}
void fragment(){
 if(tree_lod_discard(FRAGCOORD.xy)) discard;
 if (!FRONT_FACING) NORMAL=-NORMAL;
 vec4 tex=use_texture?texture(albedo_texture,UV):vec4(1.0);
 ALBEDO=tint*tex.rgb*COLOR.rgb;
 ALPHA=tex.a;
 ALPHA_SCISSOR_THRESHOLD=alpha_cutoff;
 ROUGHNESS=0.86;
 BACKLIGHT=ALBEDO*0.20;
}
