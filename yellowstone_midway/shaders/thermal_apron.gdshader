shader_type spatial;
render_mode cull_disabled;
uniform sampler2D mineral_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D surface_map : source_color, filter_linear_mipmap, repeat_disable;
varying vec3 world;
void vertex(){world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;}
void fragment(){
 vec4 mat=texture(surface_map,UV);
 vec3 stone=texture(mineral_texture,world.xz/1.8).rgb;
 ALBEDO=mat.rgb*(0.82+stone*0.30);
 ROUGHNESS=mix(0.54,0.91,mat.a);
 SPECULAR=0.22;
}
