uniform sampler2DArray ground_color_layers : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray ground_normal_layers : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray ground_arm_layers : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D rock_albedo : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2DArray geography_layers : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform sampler2D biome_map : filter_linear, repeat_disable;
uniform sampler2D detail_map : filter_linear_mipmap, repeat_enable;
uniform sampler2D trail_mask : filter_linear, repeat_disable;
uniform sampler2D snow_mask : filter_linear, repeat_disable;
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
 vec3 photo = texture(geography_layers, vec3((p.xz + vec2(2048.0)) / 4096.0, 0.0)).rgb;
 vec2 local_uv = (p.xz - vec2(detail_x_min_m, detail_z_min_m)) / vec2(detail_width_m, detail_height_m);
 if (naip_detail_available > 0.5 && all(greaterThanEqual(local_uv, vec2(0.0))) && all(lessThanEqual(local_uv, vec2(1.0)))) {
  photo = texture(geography_layers, vec3(local_uv, 1.0)).rgb;
 }
 return photo;
}

GroundSurface ground_surface(vec3 p, vec3 n) {
 GroundSurface surface;
 vec2 uv = p.xz / soil_tile_width_m;
 vec2 rotated_uv = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * uv * 0.23;
 vec3 soil = mix(texture(ground_color_layers, vec3(uv, 2.0)).rgb, texture(ground_color_layers, vec3(rotated_uv, 2.0)).rgb, 0.32);
 vec3 soil_arm = texture(ground_arm_layers, vec3(uv, 2.0)).rgb;
 vec4 biome = texture(biome_map, (p.xz + vec2(2048.0)) / 4096.0);
 float variation = texture(detail_map, p.xz / 67.0).r;
 vec3 meadow = mix(vec3(0.20, 0.235, 0.08), vec3(0.42, 0.39, 0.20), variation);
 float forest_weight = (1.0 - biome.g) * (1.0 - biome.r);
 vec3 forest = soil * vec3(0.59, 0.60, 0.47);
 vec2 soil_xy = (texture(ground_normal_layers, vec3(uv, 3.0)).rg * 2.0 - 1.0) * 0.90;
 if (forest_weight > 0.0001) {
  vec2 forest_uv = p.xz / forest_tile_width_m;
  vec2 forest_macro_uv = mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * forest_uv;
  forest = mix(texture(ground_color_layers, vec3(forest_uv, 0.0)).rgb, texture(ground_color_layers, vec3(forest_macro_uv, 0.0)).rgb, 0.32);
  vec3 forest_arm = texture(ground_arm_layers, vec3(forest_uv, 0.0)).rgb;
  vec2 forest_xy = (texture(ground_normal_layers, vec3(forest_uv, 0.0)).rg * 2.0 - 1.0) * 0.90;
  soil_arm = mix(soil_arm, forest_arm, 1.0 - biome.g);
  soil_xy = mix(soil_xy, forest_xy, 1.0 - biome.g);
 }
 vec3 ground = mix(forest, meadow * (soil * 1.45 + 0.38), biome.g);
 vec3 mineral = mix(vec3(0.61, 0.59, 0.48), vec3(0.84, 0.81, 0.68), variation);
 vec4 mineral_sample = texture(ground_normal_layers, vec3(p.xz / 4.0, 2.0));
 vec4 mineral_meso = texture(ground_normal_layers, vec3(mat2(vec2(0.8, -0.6), vec2(0.6, 0.8)) * p.xz / 19.0, 2.0));
 float mineral_grain = mineral_sample.b;
 float mineral_relief = (0.86 + 0.28 * mineral_grain) * (0.76 + 0.48 * mineral_meso.b);
 ground = mix(ground, mineral * mineral_relief, biome.r);
 float rock = 1.0 - smoothstep(0.40, 0.83, n.y);
 vec3 stone = texture(rock_albedo, p.xz / 1.8).rgb;
 ground = mix(ground, stone * 0.80, rock * 0.80);
 vec3 photo = ground_photo(p);
 float pigment = smoothstep(0.045, 0.14, photo.r - photo.b) * smoothstep(0.02, 0.09, photo.g - photo.b) * biome.r;
 photo = mix(photo, photo * vec3(1.04, 0.80, 0.76), pigment * 0.65);
 vec3 photo_detail = mix(soil * 0.95 + 0.66, vec3(mineral_relief), biome.r);
 float photo_weight = mix(macro_color_strength, 0.68, biome.r) * (1.0 - forest_weight * 0.80);
 ground = mix(ground, photo * photo_detail, photo_weight);
 float edge_detail = texture(detail_map, p.xz / 1.8).r - 0.5;
 float tread = smoothstep(0.18, 0.72, texture(trail_mask, (p.xz + vec2(2048.0)) / 4096.0).r + edge_detail * 0.06);
 vec2 trail_uv = p.xz / trail_tile_width_m;
 vec3 trail = texture(ground_color_layers, vec3(trail_uv, 1.0)).rgb;
 vec3 trail_arm = texture(ground_arm_layers, vec3(trail_uv, 1.0)).rgb;
 vec3 dirt = vec3(0.40, 0.345, 0.26) * (0.55 + 0.65 * variation);
 ground = mix(ground, mix(dirt, trail, 0.82), tread);
 float wet = clamp(ground_wetness * biome.b, 0.0, 1.0);
 surface.albedo = ground * mix(1.0, 0.73, wet);
 vec2 trail_xy = (texture(ground_normal_layers, vec3(trail_uv, 1.0)).rg * 2.0 - 1.0) * 0.65;
 vec2 mineral_xy = mineral_sample.rg * 2.0 - 1.0;
 mineral_xy += mat2(vec2(0.8, 0.6), vec2(-0.6, 0.8)) * (mineral_meso.rg * 2.0 - 1.0) * (4.0 / 19.0);
 surface.normal_xy = mix(mix(soil_xy, mineral_xy, biome.r) * (1.0 - rock * 0.80), trail_xy, tread);
 vec3 arm = mix(soil_arm, trail_arm, tread);
 surface.roughness = mix(mix(clamp(arm.g, 0.45, 0.98), mineral_sample.a, biome.r * (1.0 - tread)), 0.47, wet);
 surface.occlusion = mix(mix(1.0, arm.r, 0.55), 1.0, biome.r * (1.0 - tread));
 surface.specular = 0.25;
 float cover = texture(snow_mask, (p.xz + vec2(2048.0)) / 4096.0).r;
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
