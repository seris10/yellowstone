shader_type spatial;
render_mode diffuse_burley;
uniform sampler2D ground_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D ground_normal : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D macro_albedo : source_color, filter_linear_mipmap, repeat_disable;
uniform sampler2D biome_map : filter_linear, repeat_disable;
uniform sampler2D detail_map : filter_linear_mipmap, repeat_enable;
uniform float wetness = 0.12;
// Optional snow overlay (season.json + snow_map.png).
// snow_amount 0 uses the default look; mask is world-extent with bare thermal holes.
uniform sampler2D snow_mask : filter_linear, repeat_disable;
uniform float snow_amount = 0.0;
// Foot-trail tread painted from mapped polylines (2 m/px). Dirt trails are ground here.
uniform sampler2D trail_mask : filter_linear, repeat_disable;
varying vec3 world;
varying vec3 world_normal;
void vertex() {
 world = (MODEL_MATRIX * vec4(VERTEX,1.0)).xyz;
 world_normal = normalize((MODEL_MATRIX * vec4(NORMAL,0.0)).xyz);
 TANGENT = vec3(1.0,0.0,0.0);
 BINORMAL = vec3(0.0,0.0,1.0);
}
void fragment() {
 vec2 uv = world.xz/3.2;
 vec3 base = texture(ground_albedo,uv).rgb;
 vec3 detail = texture(ground_albedo,mat2(vec2(0.8,-0.6),vec2(0.6,0.8))*uv*0.23).rgb;
 base = mix(base, detail, 0.32);
 vec4 biome = texture(biome_map,(world.xz+vec2(2048.0))/4096.0);
 float macro = texture(detail_map,world.xz/67.0).r;
 vec3 meadow = mix(vec3(0.20,0.235,0.08),vec3(0.42,0.39,0.20),macro);
 vec3 forest = base*vec3(0.59,0.60,0.47);
 vec3 ground = mix(forest, meadow*(base*1.45+0.38),biome.g);
 vec3 mineral = mix(vec3(0.61,0.59,0.48),vec3(0.84,0.81,0.68),macro);
 ground = mix(ground,mineral*(base*0.48+0.65),biome.r);
 float rock = 1.0-smoothstep(0.40,0.83,world_normal.y);
 vec3 stone=texture(rock_albedo,world.xz/1.8).rgb;
 ground=mix(ground,stone*0.80,rock*0.80);
 vec3 macro_color=texture(macro_albedo,(world.xz+vec2(2048.0))/4096.0).rgb;
 // Art direction of the photographed mat colors.
 float pigment=smoothstep(0.045,0.14,macro_color.r-macro_color.b)*smoothstep(0.02,0.09,macro_color.g-macro_color.b)*biome.r;
 macro_color=mix(macro_color,macro_color*vec3(1.04,0.80,0.76),pigment*0.65);
  ground=mix(ground,macro_color*(base*0.65+0.78),0.78);
  float tread=smoothstep(0.18,0.72,texture(trail_mask,(world.xz+vec2(2048.0))/4096.0).r);
  vec3 dirt=vec3(0.40,0.345,0.26)*(0.55+0.65*macro);
  ground=mix(ground,dirt,tread);
  ALBEDO=ground*mix(1.0,0.73,wetness*biome.b);
  if(snow_amount>0.001){
    float cover=texture(snow_mask,(world.xz+vec2(2048.0))/4096.0).r;
    float settle=smoothstep(0.30,0.62,world_normal.y);
    float sn=clamp(snow_amount,0.0,1.0)*cover*settle;
    vec3 snowc=vec3(0.86,0.88,0.91)*(0.75+0.25*macro);
    ALBEDO=mix(ALBEDO,snowc,sn);
    ROUGHNESS=mix(ROUGHNESS,0.92,sn);
    SPECULAR=mix(SPECULAR,0.08,sn);
  }
 NORMAL_MAP=texture(ground_normal,uv).rgb;
 NORMAL_MAP_DEPTH=0.45;
 ROUGHNESS=mix(0.95,0.47,wetness*biome.b);
 SPECULAR=0.25;
}
