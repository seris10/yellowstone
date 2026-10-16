uniform bool instance_lod = false;
uniform float lod_begin_m = 0.0;
uniform float lod_end_m = 3000.0;
varying flat float tree_distance_m;

float tree_lod_width(float boundary) {
    return clamp(boundary * 0.10, 2.0, 18.0);
}

bool tree_lod_outside(float distance_m) {
    return instance_lod && ((lod_begin_m > 0.0 && distance_m < lod_begin_m - tree_lod_width(lod_begin_m))
        || distance_m > lod_end_m + tree_lod_width(lod_end_m));
}

bool tree_lod_discard(vec2 pixel) {
    if (!instance_lod) return false;
    float threshold = fract(52.9829189 * fract(dot(floor(pixel), vec2(0.06711056, 0.00583715))));
    float incoming = lod_begin_m > 0.0 ? smoothstep(lod_begin_m - tree_lod_width(lod_begin_m), lod_begin_m + tree_lod_width(lod_begin_m), tree_distance_m) : 1.0;
    float outgoing = smoothstep(lod_end_m - tree_lod_width(lod_end_m), lod_end_m + tree_lod_width(lod_end_m), tree_distance_m);
    return threshold >= incoming || threshold < outgoing;
}
