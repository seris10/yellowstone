shader_type spatial;
#include "res://shaders/wood_grain.gdshaderinc"
uniform sampler2D grain : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
// World-space planks for box decks: boards run along z and stack along x.
uniform float world_planks = 0.0;
uniform float plank_width_m = 0.15;
uniform vec3 wood_light = vec3(0.60, 0.54, 0.46);
uniform vec3 wood_dark = vec3(0.36, 0.31, 0.26);
uniform float patina = 0.40;
varying vec3 world;
void vertex(){world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;}
void fragment(){
 float station=(world_planks>0.5?world.x:UV.y)/plank_width_m;
 float along=world_planks>0.5?world.z:UV.x*2.0;
 float plank=floor(station);
 float footprint=max(fwidth(station),0.001);
 float resolve=1.0-smoothstep(0.28,0.9,footprint);
 float edge=min(fract(station),1.0-fract(station));
 float gap=1.0-smoothstep(0.013-footprint*0.5,0.013+footprint*0.5,edge);
 // Below one pixel, use area-averaged seam/color.
 float seam=1.0-mix(0.026,gap,resolve);
 float tone=fract(sin(plank*19.343)*147.11);
 float g=wood_grain(along+tone*11.0,fract(station)*plank_width_m,tone);
 float weather=patina+0.3*wood_fbm(world.xz*0.6);
 vec3 board=wood_color(g,tone,weather,wood_light,wood_dark);
 vec3 far_board=wood_color(0.5,0.5,weather,wood_light,wood_dark);
 // Weathered decking with narrow shadow gaps between boards.
 ALBEDO=mix(vec3(0.14,0.12,0.10),mix(far_board,board,resolve),seam);
 ROUGHNESS=0.84;
}
