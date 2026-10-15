// Procedural milled-wood grain shared by plank and timber shaders.

float wood_hash(vec2 p) {
 return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float wood_noise(vec2 p) {
 vec2 i = floor(p);
 vec2 f = fract(p);
 vec2 u = f * f * (3.0 - 2.0 * f);
 return mix(mix(wood_hash(i), wood_hash(i + vec2(1.0, 0.0)), u.x),
            mix(wood_hash(i + vec2(0.0, 1.0)), wood_hash(i + vec2(1.0, 1.0)), u.x), u.y);
}

float wood_fbm(vec2 p) {
 float v = 0.0;
 float a = 0.5;
 for (int i = 0; i < 4; i++) {
  v += a * wood_noise(p);
  p *= 2.03;
  a *= 0.5;
 }
 return v;
}

// Grain value in [0, 1]: warped growth-ring bands plus fine fibers along the board.
float wood_grain(float along_m, float across_m, float seed) {
 float warp = wood_fbm(vec2(along_m * 0.45, across_m * 6.0 + seed * 13.0)) * 2.2;
 float ring = fract(across_m * 22.0 + warp + seed * 3.1);
 float band = smoothstep(0.0, 0.12, ring) * smoothstep(1.0, 0.7, ring);
 float fiber = wood_noise(vec2(along_m * 2.5, across_m * 260.0 + seed * 17.0));
 return clamp(mix(band, fiber, 0.35), 0.0, 1.0);
}

// Weathered wood color from grain, per-board tone and a gray patina field.
vec3 wood_color(float grain, float tone, float patina, vec3 light, vec3 dark) {
 vec3 c = mix(dark, light, grain) * (0.86 + 0.24 * tone);
 float gray = dot(c, vec3(0.299, 0.587, 0.114));
 return mix(c, vec3(gray) * vec3(1.0, 0.98, 0.95), clamp(patina, 0.0, 1.0));
}
