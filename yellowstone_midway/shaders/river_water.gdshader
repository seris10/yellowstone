shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled;
// River surface with flow-aligned ripples, cross-section depth absorption, shore foam and feathered banks.
uniform vec3 shallow_color : source_color = vec3(0.10,0.31,0.26);
uniform vec3 deep_color : source_color = vec3(0.018,0.11,0.16);
uniform vec3 foam_color : source_color = vec3(0.82,0.86,0.82);
uniform float flow_speed = 0.55;
uniform float width_m = 15.0;
uniform float core_width_m = 12.0;
uniform float channel_depth_m = 1.1;
uniform float shelf_depth_m = 0.12;
uniform float roughness = 0.12;
uniform float temperature_c = 17.0;
uniform float clarity_m = 0.9;
uniform float bank_feather_m = 1.6;
uniform sampler2D ripple : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
varying vec3 world;
varying vec3 flow_dir;
varying float incline;
varying float end_fade;
void vertex(){
 world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
 incline=1.0-normalize(MODEL_NORMAL_MATRIX*NORMAL).y;
 flow_dir=normalize((MODEL_MATRIX*vec4(TANGENT,0.0)).xyz);
 end_fade=COLOR.b;
 TANGENT=vec3(1.0,0.0,0.0);BINORMAL=vec3(0.0,0.0,1.0);
}
void fragment(){
 vec2 f=normalize(flow_dir.xz+vec2(0.00001,0.0));
 vec2 s=vec2(-f.y,f.x);
 vec2 p=vec2(dot(world.xz,s),dot(world.xz,f));
 float t=TIME*flow_speed;
 vec3 n1=texture(ripple,(p+vec2(0.0,-t))*0.31).rgb;
 vec3 n2=texture(ripple,(p*1.85+vec2(0.37,-t*1.3))*0.31).rgb;
 vec3 n3=texture(ripple,(p*0.42+vec2(0.11,-t*0.6))*0.31).rgb;
 vec2 tilt=((n1.rg+n2.rg)*0.5-vec2(0.5))*2.0+((n3.rg-vec2(0.5))*2.0)*0.6;
 vec2 wxz=s*tilt.x+f*tilt.y;
 float near_detail=1.0-smoothstep(40.0,220.0,length(VERTEX));
 NORMAL_MAP=vec3(wxz.x,wxz.y,1.0)*0.5+vec3(0.5);
 NORMAL_MAP_DEPTH=0.13*mix(0.30,1.0,near_detail);

 float across=abs(UV.x*2.0-1.0);
 float across_m=across*0.5*width_m;
 float half_core=core_width_m*0.5;
 float broken=n1.r*0.55+n2.g*0.45;
 float edge_m=(1.0-across)*0.5*width_m;
 float bank=smoothstep(0.0,bank_feather_m,edge_m+(broken-0.5)*1.5);
 float channel=1.0-smoothstep(half_core-1.5,half_core+1.0,across_m);
 // Depth follows the carved cross-section: V-shaped channel over a flat shelf.
 float depth_m=shelf_depth_m+channel_depth_m*clamp(1.0-across_m/half_core,0.0,1.0);
 float absorb=1.0-exp(-depth_m/clarity_m);
 vec3 color=mix(shallow_color,deep_color,clamp(absorb+channel*0.30,0.0,1.0));
 // Firehole authored tint between 7 and 32 degC.
 float warmth=clamp((temperature_c-7.0)/25.0,0.0,1.0);
 color=mix(color,vec3(0.33,0.37,0.26),warmth*0.25);

 float shore_line=1.0-smoothstep(0.0,0.9,edge_m);
 float crest=smoothstep(0.50,0.74,broken);
 float riffle=smoothstep(0.004,0.03,incline)*smoothstep(0.44,0.70,broken);
 float foam=clamp(shore_line*0.55*crest+riffle*0.8,0.0,1.0);
 color=mix(color,foam_color,foam*0.55);

 float fres=pow(1.0-clamp(dot(NORMAL,VIEW),0.0,1.0),5.0);
 float alpha=0.16+0.80*(1.0-exp(-depth_m*2.2));
 alpha=max(alpha,channel*0.90);
 alpha=mix(alpha,1.0,fres*0.35);
 alpha=max(alpha,foam*0.6);
 ALBEDO=color;
 ROUGHNESS=mix(roughness,0.55,foam);
 SPECULAR=0.5;
 METALLIC=0.0;
 ALPHA=clamp(alpha*bank*smoothstep(0.0,1.0,end_fade),0.0,1.0);
}
