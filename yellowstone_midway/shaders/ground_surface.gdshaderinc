uniform sampler2DArray ground_color_layers : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray ground_normal_layers : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray ground_arm_layers : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray geography_layers : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D biome_map : filter_linear, repeat_disable;
uniform sampler2D detail_map : filter_linear_mipmap, repeat_enable;
uniform sampler2D trail_mask : filter_linear, repeat_disable;
uniform sampler2D snow_mask : filter_linear, repeat_disable;
// Layer rectangles are minimum corner and size in meters, relative to the current render origin.
uniform vec2 geography_origin_m = vec2(-2048.0);
uniform vec2 geography_extent_m = vec2(4096.0);
uniform vec2 biome_origin_m = vec2(-2048.0);
uniform vec2 biome_extent_m = vec2(4096.0);
uniform vec2 trail_origin_m = vec2(-2048.0);
uniform vec2 trail_extent_m = vec2(4096.0);
uniform vec2 snow_origin_m = vec2(-2048.0);
uniform vec2 snow_extent_m = vec2(4096.0);
// Repeat phases are the render origin in texture periods, reduced modulo one period on the CPU.
uniform vec2 soil_phase = vec2(0.0);
uniform vec2 soil_rotated_phase = vec2(0.0);
uniform vec2 forest_phase = vec2(0.0);
uniform vec2 forest_rotated_phase = vec2(0.0);
uniform vec2 trail_phase = vec2(0.0);
uniform vec2 variation_phase = vec2(0.0);
uniform vec2 mineral_phase = vec2(0.0);
uniform vec2 mineral_meso_phase = vec2(0.0);
uniform vec2 fine_detail_phase = vec2(0.0);
uniform float naip_detail_available = 0.0;
uniform float detail_x_min_m = -640.0;
uniform float detail_z_min_m = -640.0;
uniform float detail_width_m = 1280.0;
uniform float detail_height_m = 1280.0;
uniform float soil_tile_width_m = 3.15;
uniform float forest_tile_width_m = 2.0;
uniform float trail_tile_width_m = 2.0;
uniform float macro_color_strength = 0.28;
uniform float ground_wetness = 0.12;
uniform float snow_amount = 0.0;
uniform float snow_swe_mm = 0.0;
uniform float snow_cover_fraction = 1.0;
// Close-range detail normal, fading with view distance.
uniform float detail_normal_strength : hint_range(0.0, 2.0) = 0.75;
uniform float detail_normal_tile_m = 0.42;
uniform float detail_normal_near_m = 2.0;
uniform float detail_normal_far_m = 12.0;
uniform vec2 detail_normal_phase = vec2(0.0);
uniform vec2 detail_normal_fine_phase = vec2(0.0);
// Triplanar bank rock.
uniform float rock_tile_width_m = 1.8;
uniform float rock_triplanar_sharpness = 4.0;
uniform vec2 rock_tri_phase = vec2(0.0);
// Spatial water height and support mask use the geographic frame.
uniform sampler2D water_level_texture : filter_nearest, repeat_disable;
uniform vec2 water_level_origin_m = vec2(-2048.0);
uniform vec2 water_level_extent_m = vec2(4096.0);
uniform float water_level_available = 0.0;
uniform float bank_wet_height_m = 0.35;
uniform float bank_stain_height_m = 1.20;
uniform float bank_strata_frequency = 9.0; // cycles per meter of bank height
uniform float bank_effect_strength : hint_range(0.0, 1.0) = 0.8;
// Optional parallax occlusion over the mineral apron grain.
uniform float pom_strength : hint_range(0.0, 1.0) = 0.0;
uniform float pom_height_scale_m = 0.02; // matches the measured 0.017 to 0.0195 m grain range
uniform float pom_max_distance_m = 6.0;

struct GroundSurface {
 vec3 albedo;
 vec3 spatial_detail;
 float mineral_grain;
 vec2 normal_xy;
 float roughness;
 float occlusion;
 float specular;
 float mineral;
 float tread;
 float snow;
};

vec3 ground_tangent(vec3 n) {
 vec3 axis = abs(n.x) < 0.95 ? vec3(1.0, 0.0, 0.0) : vec3(0.0, 0.0, 1.0);
 return normalize(axis - n * dot(n, axis));
}

vec3 ground_photo(vec3 p) {
 vec3 photo = texture(geography_layers, vec3((p.xz - geography_origin_m) / geography_extent_m, 0.0)).rgb;
 vec2 local_uv = (p.xz - vec2(detail_x_min_m, detail_z_min_m)) / vec2(detail_width_m, detail_height_m);
 if (naip_detail_available > 0.5 && all(greaterThanEqual(local_uv, vec2(0.0))) && all(lessThanEqual(local_uv, vec2(1.0)))) {
  photo = texture(geography_layers, vec3(local_uv, 1.0)).rgb;
 }
 return photo;
}

// Two-octave detail normal over layer 1, fading with view distance.
vec2 close_detail_normal(vec3 p, float view_dist) {
 float fade = 1.0 - smoothstep(detail_normal_near_m, detail_normal_far_m, view_dist);
 if (fade <= 0.001) {
  return vec2(0.0);
 }
 vec2 uv1 = p.xz / detail_normal_tile_m + detail_normal_phase;
 vec2 o1 = texture(ground_normal_layers, vec3(uv1, 1.0)).rg * 2.0 - 1.0;
 vec2 uv2 = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * p.xz / (detail_normal_tile_m * 0.21) + detail_normal_fine_phase;
 vec2 o2 = texture(ground_normal_layers, vec3(uv2, 1.0)).rg * 2.0 - 1.0;
 return (o1 * 0.7 + o2 * 0.3) * detail_normal_strength * fade;
}

// Triplanar rock albedo; steep banks avoid the planar streaking of a top-down lookup.
vec3 rock_triplanar(vec3 p, vec3 n) {
 vec3 w = pow(abs(n), vec3(rock_triplanar_sharpness));
 w /= (w.x + w.y + w.z);
 vec2 uv_x = vec2(p.z, p.y) / rock_tile_width_m + vec2(rock_tri_phase.y, 0.0);
 vec2 uv_y = p.xz / rock_tile_width_m + rock_tri_phase;
 vec2 uv_z = vec2(p.x, p.y) / rock_tile_width_m + vec2(rock_tri_phase.x, 0.0);
 return texture(rock_albedo, uv_x).rgb * w.x
  + texture(rock_albedo, uv_y).rgb * w.y
  + texture(rock_albedo, uv_z).rgb * w.z;
}

vec2 rock_triplanar_normal(vec3 p, vec3 n) {
 vec3 w = pow(abs(n), vec3(rock_triplanar_sharpness));
 w /= (w.x + w.y + w.z);
 vec2 uv_x = vec2(p.z, p.y) / rock_tile_width_m + vec2(rock_tri_phase.y, 0.0);
 vec2 uv_y = p.xz / rock_tile_width_m + rock_tri_phase;
 vec2 uv_z = vec2(p.x, p.y) / rock_tile_width_m + vec2(rock_tri_phase.x, 0.0);
 vec2 nx = texture(ground_normal_layers, vec3(uv_x, 1.0)).rg * 2.0 - 1.0;
 vec2 ny = texture(ground_normal_layers, vec3(uv_y, 1.0)).rg * 2.0 - 1.0;
 vec2 nz = texture(ground_normal_layers, vec3(uv_z, 1.0)).rg * 2.0 - 1.0;
 return (nx * w.x + ny * w.y + nz * w.z) * 0.6;
}

// Parallax offset over the mineral grain height in layer 2.
vec2 mineral_pom_offset(vec3 p, vec3 cam_world) {
 vec3 to_cam = cam_world - p;
 float dist = length(to_cam);
 float fade = (1.0 - smoothstep(pom_max_distance_m * 0.6, pom_max_distance_m, dist)) * pom_strength;
 if (fade <= 0.001) {
  return vec2(0.0);
 }
 vec3 vd = to_cam / dist;
 vec2 dir = -vd.xz / max(vd.y, 0.20);
 const int STEPS = 8;
 float step_h = 1.0 / float(STEPS);
 vec2 uv_off = vec2(0.0);
 float ray_h = 0.0;
 for (int i = 0; i < STEPS; i++) {
  float surf_h = textureLod(ground_normal_layers, vec3((p.xz + uv_off) / 4.0 + mineral_phase, 2.0), 2.0).b;
  if (ray_h >= 1.0 - surf_h) {
   break;
  }
  ray_h += step_h;
  uv_off = dir * ray_h * pom_height_scale_m * fade;
 }
 return uv_off;
}

GroundSurface ground_surface(vec3 p, vec3 n, vec3 cam) {
 GroundSurface surface;
 float view_dist = distance(p, cam);
 vec2 soil_local = p.xz / soil_tile_width_m;
 vec2 uv = soil_local + soil_phase;
 vec2 rotated_uv = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * soil_local * 0.23 + soil_rotated_phase;
 vec3 soil = mix(texture(ground_color_layers, vec3(uv, 2.0)).rgb, texture(ground_color_layers, vec3(rotated_uv, 2.0)).rgb, 0.32);
 vec3 soil_arm = texture(ground_arm_layers, vec3(uv, 2.0)).rgb;
 vec4 biome = texture(biome_map, (p.xz - biome_origin_m) / biome_extent_m);
 float variation = texture(detail_map, p.xz / 67.0 + variation_phase).r;
 vec3 meadow = mix(vec3(0.20, 0.235, 0.08), vec3(0.42, 0.39, 0.20), variation);
 float forest_weight = (1.0 - biome.g) * (1.0 - biome.r);
 vec3 forest = soil * vec3(0.59, 0.60, 0.47);
 vec2 soil_xy = (texture(ground_normal_layers, vec3(uv, 3.0)).rg * 2.0 - 1.0) * 0.90;
 if (forest_weight > 0.0001) {
  vec2 forest_local = p.xz / forest_tile_width_m;
  vec2 forest_uv = forest_local + forest_phase;
  vec2 forest_macro_uv = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * forest_local + forest_rotated_phase;
  forest = mix(texture(ground_color_layers, vec3(forest_uv, 0.0)).rgb, texture(ground_color_layers, vec3(forest_macro_uv, 0.0)).rgb, 0.32);
  vec3 forest_arm = texture(ground_arm_layers, vec3(forest_uv, 0.0)).rgb;
  vec2 forest_xy = (texture(ground_normal_layers, vec3(forest_uv, 0.0)).rg * 2.0 - 1.0) * 0.90;
  soil_arm = mix(soil_arm, forest_arm, 1.0 - biome.g);
  soil_xy = mix(soil_xy, forest_xy, 1.0 - biome.g);
 }
 vec3 ground = mix(forest, meadow * (soil * 1.45 + 0.38), biome.g);
 vec3 mineral = mix(vec3(0.61, 0.59, 0.48), vec3(0.84, 0.81, 0.68), variation);
 // Optional parallax shift of the lookup point before mineral sampling.
 vec2 pom_off = mineral_pom_offset(p, cam) * biome.r;
 vec3 p_s = p + vec3(pom_off.x, 0.0, pom_off.y);
 vec4 mineral_sample = texture(ground_normal_layers, vec3(p_s.xz / 4.0 + mineral_phase, 2.0));
 vec4 mineral_meso = texture(ground_normal_layers, vec3(mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * p_s.xz / 19.0 + mineral_meso_phase, 2.0));
 float mineral_grain = mineral_sample.b;
 float mineral_relief = (0.86 + 0.28 * mineral_grain) * (0.76 + 0.48 * mineral_meso.b);
 ground = mix(ground, mineral * mineral_relief, biome.r);
 float rock = 1.0 - smoothstep(0.40, 0.83, n.y);
 vec3 stone = rock_triplanar(p, n);
 ground = mix(ground, stone * 0.80, rock * 0.80);
 // Wet and stain bands on banks by height above the water surface.
 vec2 water_uv = (p.xz - water_level_origin_m) / water_level_extent_m;
 vec2 stage = texture(water_level_texture, water_uv).rg;
 float stage_support = water_level_available * stage.g * float(all(greaterThanEqual(water_uv, vec2(0.0))) && all(lessThanEqual(water_uv, vec2(1.0))));
 float above_water = p.y - stage.r;
 float wet_band = stage_support * (1.0 - smoothstep(0.0, bank_wet_height_m, above_water)) * smoothstep(-0.6, -0.05, above_water);
 float strata_noise = texture(detail_map, vec2(p.x + p.z, p.y * 2.0) / 19.0 + variation_phase).r;
 float strata = 0.5 + 0.5 * sin(above_water * bank_strata_frequency * 6.2831 + strata_noise * 5.0);
 float stain_band = stage_support * smoothstep(0.02, 0.25, above_water) * (1.0 - smoothstep(bank_stain_height_m * 0.5, bank_stain_height_m, above_water));
 ground *= 1.0 - bank_effect_strength * rock * (0.28 * wet_band + 0.12 * strata * stain_band);
 vec3 photo = ground_photo(p);
 float pigment = smoothstep(0.045, 0.14, photo.r - photo.b) * smoothstep(0.02, 0.09, photo.g - photo.b) * biome.r;
 photo = mix(photo, photo * vec3(1.04, 0.80, 0.76), pigment * 0.65);
 vec3 photo_detail = mix(soil * 0.95 + 0.66, vec3(mineral_relief), biome.r);
 // The photo wash fades out at close range.
 float photo_weight = mix(macro_color_strength, 0.68, biome.r) * (1.0 - forest_weight * 0.80) * smoothstep(1.5, 8.0, view_dist);
 ground = mix(ground, photo * photo_detail, photo_weight);
 float edge_detail = texture(detail_map, p.xz / 1.8 + fine_detail_phase).r - 0.5;
 float tread = smoothstep(0.18, 0.72, texture(trail_mask, (p.xz - trail_origin_m) / trail_extent_m).r + edge_detail * 0.06);
 vec2 trail_uv = p.xz / trail_tile_width_m + trail_phase;
 vec3 trail = texture(ground_color_layers, vec3(trail_uv, 1.0)).rgb;
 vec3 trail_arm = texture(ground_arm_layers, vec3(trail_uv, 1.0)).rgb;
 vec3 dirt = vec3(0.40, 0.345, 0.26) * (0.55 + 0.65 * variation);
 ground = mix(ground, mix(dirt, trail, 0.82), tread);
 float wet = clamp(ground_wetness * biome.b, 0.0, 1.0);
 surface.albedo = ground * mix(1.0, 0.73, wet);
 vec2 trail_xy = (texture(ground_normal_layers, vec3(trail_uv, 1.0)).rg * 2.0 - 1.0) * 0.65;
 vec2 mineral_xy = mineral_sample.rg * 2.0 - 1.0;
 mineral_xy += mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8)) * (mineral_meso.rg * 2.0 - 1.0) * (4.0 / 19.0);
 surface.normal_xy = mix(mix(soil_xy, mineral_xy, biome.r) * (1.0 - rock * 0.35), trail_xy, tread);
 // Banks keep relief through the triplanar octave and the close-range detail.
 surface.normal_xy += rock_triplanar_normal(p, n) * rock;
 surface.normal_xy += close_detail_normal(p, view_dist);
 vec3 arm = mix(soil_arm, trail_arm, tread);
 surface.roughness = mix(mix(clamp(arm.g, 0.45, 0.98), mineral_sample.a, biome.r * (1.0 - tread)), 0.47, wet);
 surface.roughness = mix(surface.roughness, 0.35, wet_band * rock * bank_effect_strength);
 surface.occlusion = mix(mix(1.0, arm.r, 0.55), 0.80 + 0.35 * mineral_grain, biome.r * (1.0 - tread));
 surface.specular = 0.25;
 float cover = texture(snow_mask, (p.xz - snow_origin_m) / snow_extent_m).r;
 float settle = smoothstep(0.30, 0.62, n.y);
 float swe_gate = smoothstep(5.0, 15.0, snow_swe_mm);
 surface.snow = clamp(snow_amount, 0.0, 1.0) * cover * settle * swe_gate * clamp(snow_cover_fraction, 0.0, 1.0);
 vec3 snow_color = vec3(0.86, 0.88, 0.91) * (0.75 + 0.25 * variation);
 surface.albedo = mix(surface.albedo, snow_color, surface.snow);
 surface.normal_xy *= 1.0 - surface.snow;
 surface.roughness = mix(surface.roughness, 0.92, surface.snow);
 surface.occlusion = mix(surface.occlusion, 1.0, surface.snow);
 surface.specular = mix(surface.specular, 0.08, surface.snow);
 surface.spatial_detail = vec3(1.0);
 vec2 detail_uv = (p.xz - vec2(detail_x_min_m, detail_z_min_m)) / vec2(detail_width_m, detail_height_m);
 if (naip_detail_available > 0.5 && all(greaterThanEqual(detail_uv, vec2(0.0))) && all(lessThanEqual(detail_uv, vec2(1.0)))) {
  surface.spatial_detail = texture(geography_layers, vec3(detail_uv, 2.0)).rgb * 2.0;
 }
 surface.mineral_grain = mineral_relief;
 surface.mineral = clamp(biome.r, 0.0, 1.0);
 surface.tread = tread;
 return surface;
}
