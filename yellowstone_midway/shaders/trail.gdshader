shader_type spatial;
uniform sampler2D ground_detail : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
void fragment(){
 // Saved ribbon UV.y is metres. The tread sits 3 cm proud of the ground.
 vec3 grains=texture(ground_detail,vec2(UV.x*1.15,UV.y*0.5)).rgb;
 vec3 col=vec3(0.36,0.30,0.225)*(grains*0.5+vec3(0.62));
 float edge=min(UV.x,1.0-UV.x);
 col*=mix(0.70,1.0,smoothstep(0.0,0.16,edge));
 ALBEDO=col;
 ROUGHNESS=0.97;
 SPECULAR=0.15;
}
