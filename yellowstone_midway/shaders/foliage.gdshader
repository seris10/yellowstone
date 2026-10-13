shader_type spatial;
render_mode cull_disabled, diffuse_lambert_wrap;
uniform sampler2D albedo_texture : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform bool use_texture = false;
uniform vec3 tint : source_color = vec3(0.25,0.32,0.15);
uniform float wind_strength = 0.2;
uniform vec2 wind_vector=vec2(1.8,0.6);
varying vec3 world;
void vertex(){
 world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
 float weight=clamp(VERTEX.y/(wind_strength<0.1?0.8:7.0),0.0,1.0);
 float bend=sin(TIME*1.7+world.x*0.2+world.z*0.15)*wind_strength*weight*weight;
 // Wind points east and south in world space; inverse(mat3(MODEL_MATRIX)) maps the world-space wind offset back into local space per instance. Baked flora scales stay in [0.6, 1.3], keeping the matrix well-conditioned; a scale near zero would blow up here.
 VERTEX+=inverse(mat3(MODEL_MATRIX))*vec3(bend*wind_vector.x,0.0,bend*wind_vector.y);
}
void fragment(){
 vec4 tex=use_texture?texture(albedo_texture,UV):vec4(1.0);
 ALBEDO=tint*tex.rgb*COLOR.rgb;
 ALPHA=tex.a;
 ALPHA_SCISSOR_THRESHOLD=0.40;
 ROUGHNESS=0.86;
 BACKLIGHT=ALBEDO*0.20;
}
