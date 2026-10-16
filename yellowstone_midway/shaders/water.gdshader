shader_type spatial;
render_mode cull_disabled,depth_draw_opaque;
uniform vec3 shallow_color : source_color = vec3(0.10,0.31,0.26);
uniform vec3 deep_color : source_color = vec3(0.018,0.11,0.16);
uniform float flow_speed = 0.55;
uniform float width_m = 15.0;
uniform float roughness = 0.2;
uniform float pool = 0.0;
uniform float temperature_c = 17.0;
uniform float cascade = 0.0;
uniform sampler2D ripple : hint_normal, filter_linear_mipmap, repeat_enable;
// Optional per-pool authored pigment ramp (pool_shells.json + pool_ramps/); ramp_mix 0 uses the default two-color look, ramp x=0 is the hot center, x=1 the outer rim.
uniform sampler2D band_ramp : source_color, filter_linear, repeat_disable;
uniform float ramp_mix = 0.0;
uniform sampler2D display_band_ramp : source_color, filter_linear, repeat_disable;
uniform float display_ramp_mix = 0.0;
varying vec3 world;
varying float incline;
void vertex(){
 world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
 incline=1.0-normalize(MODEL_NORMAL_MATRIX*NORMAL).y;
 TANGENT=vec3(1.0,0.0,0.0);BINORMAL=vec3(0.0,0.0,1.0);
}
void fragment(){
 // Ribbon UV.y is meter arc length in the saved downhill point order; pools use slow local wind ripples.
 vec2 metres=pool>0.5?world.xz:vec2(UV.x*width_m,UV.y);
 vec2 drift=pool>0.5?vec2(0.02,-0.01)*TIME:vec2(0.012,-flow_speed)*TIME;
 vec3 n1=texture(ripple,(metres+drift)*0.35).rgb;
 vec3 n2=texture(ripple,(metres+drift*0.73)*0.70+vec2(0.23,0.17)).rgb;
  float side=pool>0.5?COLOR.r:smoothstep(0.0,0.72,1.0-abs(UV.x*2.0-1.0));
  vec3 color=mix(shallow_color,deep_color,side);
  if(pool>0.5&&ramp_mix>0.001){
    vec3 band=texture(band_ramp,vec2(clamp(1.0-side,0.0,1.0),0.5)).rgb;
    color=mix(color,band,ramp_mix);
    if(display_ramp_mix>0.001){
      vec3 display_band=texture(display_band_ramp,vec2(clamp(1.0-side,0.0,1.0),0.5)).rgb;
      color=mix(color,display_band,display_ramp_mix);
    }
  }
  // Firehole river authored tint between 7 and 32 degC.
  if(pool<0.5&&cascade<0.5){
    float warmth=clamp((temperature_c-7.0)/25.0,0.0,1.0);
    color=mix(color,vec3(0.33,0.37,0.26),warmth*0.25);
  }
 float wave=sin(UV.y*9.0-TIME*flow_speed*8.0)*sin(UV.y*3.3+world.x*1.1);
 color+=vec3(0.055)*pow(max(0.0,wave),12.0)*(1.0-pool)*0.30;
  float broken_crests=n1.r*0.55+n2.g*0.45;
  float foam=cascade*smoothstep(0.0015,0.025,incline)*smoothstep(0.56,0.72,broken_crests);
  color=mix(color,vec3(0.80,0.83,0.78),foam*0.15);
  if(cascade>0.5){
    // Thermal outflow ribbon: vertex color red runs 1 at source to 0 at mouth.
    float downstream=1.0-COLOR.r;
    vec3 hot=vec3(0.30,0.42,0.33);
    vec3 cool=vec3(0.10,0.30,0.27);
    color=mix(hot,cool,smoothstep(0.0,0.85,downstream));
    float streak=sin(UV.y*7.0+world.x*2.0)*sin(UV.y*2.3-world.z*1.4);
    float foam_band=smoothstep(0.45,0.75,broken_crests)*(1.0-downstream*0.65);
    color=mix(color,vec3(0.82,0.85,0.80),clamp(foam_band,0.0,1.0)*0.35);
    color+=vec3(0.06)*pow(max(0.0,streak),8.0);
  }
 ALBEDO=color;
 NORMAL_MAP=mix(n1,n2,0.5);
 NORMAL_MAP_DEPTH=pool>0.5?0.035:0.16;
 ROUGHNESS=roughness;
 METALLIC=0.0;
 ALPHA=pool>0.5&&ramp_mix>0.5?1.0:mix(mix(0.82,0.97,pool),0.72+foam*0.22,cascade);
 SPECULAR=0.25;
}
