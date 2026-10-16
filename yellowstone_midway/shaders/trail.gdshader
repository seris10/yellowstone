shader_type spatial;
uniform sampler2D ground_detail : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
// Trail width in meters; bake_world sets this per route material.
uniform float width_m = 2.0;
// Edge soften band width in meters.
uniform float edge_width_m = 0.12;
void fragment(){
 // Saved ribbon UV.y is meters. The tread sits 3 cm proud of the ground.
 vec3 grains=texture(ground_detail,vec2(UV.x*1.15,UV.y*0.5)).rgb;
 vec3 col=vec3(0.36,0.30,0.225)*(grains*0.5+vec3(0.62));
 // Soften distance from either edge in meters; UV.x is [0, 1] across width_m.
 float edge_m=min(UV.x,1.0-UV.x)*max(width_m,0.001);
 col*=mix(0.70,1.0,smoothstep(0.0,edge_width_m,edge_m));
 ALBEDO=col;
 ROUGHNESS=0.97;
 SPECULAR=0.15;
}
