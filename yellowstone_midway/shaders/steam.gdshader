shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_never, shadows_disabled;
uniform sampler2D cloud_texture : filter_linear_mipmap, repeat_enable;
uniform float density = 0.30;
uniform vec2 wind = vec2(1.8,0.6);
varying float phase;
// INSTANCE_CUSTOM.x is the per-plume phase in [0, 1], written by bake_world.append_instance.
void vertex(){
 phase=INSTANCE_CUSTOM.x;
 float t=mod(TIME*0.14+phase,1.0);
 // Camera-facing vapor cards advect in the shared world wind. Rotating the card must not rotate its wind direction.
 vec3 center=MODEL_MATRIX[3].xyz+vec3(wind.x*t*7.0,t*5.0,wind.y*t*7.0);
 vec3 right=normalize(vec3(INV_VIEW_MATRIX[0].x,0.0,INV_VIEW_MATRIX[0].z));
 vec3 point=center+right*VERTEX.x*length(MODEL_MATRIX[0].xyz)+vec3(0.0,VERTEX.y*length(MODEL_MATRIX[1].xyz),0.0);
 POSITION=PROJECTION_MATRIX*VIEW_MATRIX*vec4(point,1.0);
}
void fragment(){
 float t=mod(TIME*0.14+phase,1.0);
 vec2 q=UV-vec2(0.5);
 float edge=1.0-smoothstep(0.22,0.50,length(q));
 float noise=texture(cloud_texture,UV*1.8+vec2(TIME*0.014,phase)).r;
 float fade=sin(t*3.1415926);
 ALBEDO=vec3(0.92,0.955,0.96);
 ALPHA=edge*noise*fade*density;
}
