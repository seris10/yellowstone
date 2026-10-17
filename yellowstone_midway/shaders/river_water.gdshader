shader_type spatial;
render_mode blend_mix, depth_draw_never, cull_disabled;
// Depth-colored river water with flow normals, foam, and shore feathering.
uniform vec3 shallow_color : source_color = vec3(0.18, 0.42, 0.36);
uniform vec3 deep_color : source_color = vec3(0.020, 0.130, 0.180);
uniform vec3 sky_reflect_color : source_color = vec3(0.55, 0.68, 0.78);
uniform vec3 foam_color : source_color = vec3(0.88, 0.92, 0.90);
uniform float flow_speed = 0.55;          // m/s, driven per reach at runtime
uniform float width_m = 15.0;             // visual width including bank margin
uniform float core_width_m = 12.0;        // authored channel width
uniform float channel_depth_m = 1.1;      // fallback center depth
uniform float clarity_m = 1.4;            // Beer-Lambert e-folding length in m
uniform float edge_soften_m = 0.6;        // shoreline feather by water depth
uniform float normal_strength = 0.35;
uniform float roughness_base = 0.08;
uniform float fresnel_power = 5.0;
uniform float fresnel_reflectance = 0.35; // grazing-angle sky contribution
uniform float glint_strength = 1.0;
uniform float foam_amount = 0.6;
uniform float slope_foam_boost = 2.0;
uniform float temperature_c = 17.0;
uniform sampler2D ripple : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D depth_texture : hint_depth_texture, repeat_disable, filter_nearest;
varying vec3 world;
varying vec3 flow_dir;
varying float incline;
varying float end_fade;
void vertex(){
 world=(MODEL_MATRIX*vec4(VERTEX,1.0)).xyz;
 incline=1.0-normalize(MODEL_NORMAL_MATRIX*NORMAL).y;
 flow_dir=normalize((MODEL_MATRIX*vec4(TANGENT,0.0)).xyz);
 end_fade=COLOR.b;
 // Preserve baked tangents for flow-aligned normals.
}
void fragment(){
 vec2 f=normalize(flow_dir.xz+vec2(0.00001,0.0));
 vec2 s=vec2(-f.y,f.x);
 vec2 p=vec2(dot(world.xz,s),dot(world.xz,f));
 // Increase advection speed with surface slope.
 float speed=flow_speed*(1.0+6.0*incline);
 float t=TIME*speed;
 // Stretch three scrolling ripple octaves along the flow.
 vec2 uv1=vec2(p.x*0.55,(p.y-t*1.00)*0.22);
 vec2 uv2=vec2(p.x*1.30,(p.y-t*1.45)*0.61)+vec2(0.37,0.11);
 vec2 uv3=vec2(p.x*2.90,(p.y-t*2.10)*1.35)+vec2(0.71,0.53);
 vec3 n1=texture(ripple,uv1).rgb;
 vec3 n2=texture(ripple,uv2).rgb;
 vec3 n3=texture(ripple,uv3).rgb;
 vec2 tilt=(n1.rg-0.5)*1.4+(n2.rg-0.5)*0.9+(n3.rg-0.5)*0.5;
 float view_dist=length(VERTEX);
 float detail=1.0-smoothstep(30.0,260.0,view_dist);
 vec2 wxz=s*tilt.x+f*tilt.y;
 NORMAL_MAP=vec3(wxz.x,wxz.y,1.0)*0.5+vec3(0.5);
 NORMAL_MAP_DEPTH=normal_strength*mix(0.25,1.0,detail);
 // Perturb the view-space normal for Fresnel reflection.
 vec3 n_view=normalize(TANGENT*wxz.x+BINORMAL*wxz.y+NORMAL);
 // Reconstruct the opaque depth behind the water.
 float depth_raw=textureLod(depth_texture,SCREEN_UV,0.0).r;
 vec3 ndc=vec3(SCREEN_UV*2.0-1.0,depth_raw); // Forward+ and Mobile NDC
 vec4 vpos=INV_PROJECTION_MATRIX*vec4(ndc,1.0);
 vpos.xyz/=vpos.w;
 float scene_depth=-vpos.z;
 float frag_depth=-VERTEX.z;
 float water_depth=scene_depth-frag_depth;
 // Use an authored cross-section when sampled depth is outside the display range.
 float across=abs(UV.x*2.0-1.0);
 float across_m=across*0.5*width_m;
 float half_core=core_width_m*0.5;
 float authored_depth=0.12+channel_depth_m*clamp(1.0-across_m/half_core,0.0,1.0);
 if(water_depth<0.0||water_depth>8.0){
  water_depth=authored_depth;
 }
 // Apply Beer-Lambert absorption over the water column.
 float absorb=1.0-exp(-water_depth/clarity_m);
 vec3 color=mix(shallow_color,deep_color,clamp(absorb,0.0,1.0));
 // Apply the authored Firehole tint from 7 to 32 degC.
 float warmth=clamp((temperature_c-7.0)/25.0,0.0,1.0);
 color=mix(color,vec3(0.33,0.37,0.26),warmth*0.2);
 // Use authored sky color for Fresnel reflection.
 float fres=pow(1.0-clamp(dot(n_view,normalize(VIEW)),0.0,1.0),fresnel_power);
 color=mix(color,sky_reflect_color,fres*fresnel_reflectance);
 // Advect crest foam and derive shoreline foam from depth.
 float crest=smoothstep(0.58,0.78,n1.r*0.5+n2.g*0.3+n3.r*0.2);
 float riffle=smoothstep(0.004,0.03,incline);
 float shore_foam=1.0-smoothstep(0.0,0.45,water_depth);
 float foam=clamp(crest*(0.25+riffle*slope_foam_boost)+shore_foam*0.7,0.0,1.0)*foam_amount;
 color=mix(color,foam_color,foam*0.75);
 float alpha=mix(0.35,0.97,clamp(absorb*1.6,0.0,1.0));
 alpha=max(alpha,foam*0.85);
 alpha=mix(alpha,1.0,fres*0.25);
 // Feather alpha by column depth and baked end fade.
 float edge=smoothstep(0.0,edge_soften_m,water_depth);
 alpha*=edge*smoothstep(0.0,1.0,end_fade);
 ALBEDO=color;
 // Modulate glint roughness with the fine ripple octave.
 ROUGHNESS=clamp(mix(roughness_base,0.5,foam)+(n3.g-0.5)*0.2*glint_strength,0.03,1.0);
 SPECULAR=0.5;
 METALLIC=0.0;
 ALPHA=clamp(alpha,0.0,1.0);
}
