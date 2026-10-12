shader_type spatial;
uniform sampler2D grain : source_color,filter_linear_mipmap_anisotropic,repeat_enable;
varying vec3 world;
void vertex(){world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;}
void fragment(){
 float station=UV.y/0.15;
 float plank=floor(station);
 float footprint=max(fwidth(station),0.001);
 float resolve=1.0-smoothstep(0.28,0.9,footprint);
 float edge=min(fract(station),1.0-fract(station));
 float gap=1.0-smoothstep(0.013-footprint*0.5,0.013+footprint*0.5,edge);
 // Below one pixel, use area-averaged seam/color.
 float seam=1.0-mix(0.026,gap,resolve);
 float variation=mix(0.90,0.80+0.20*fract(sin(plank*19.343)*147.11),resolve);
 vec3 tex=texture(grain,vec2(UV.x*0.18,UV.y*0.18)).rgb;
 // Weathered-gray composite decking, dark timber rails on bark_mat. Seams read as narrow shadow gaps.
 ALBEDO=mix(vec3(0.23),vec3(0.55,0.54,0.51)*(tex*0.5+0.75)*variation,seam);
 ROUGHNESS=0.84;
}
