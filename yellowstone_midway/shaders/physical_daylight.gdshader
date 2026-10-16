shader_type sky;
render_mode use_debanding;

uniform float turbidity = 2.2;
uniform float exposure = 1.0;
uniform float daylight = 1.0;
uniform sampler2D night_sky : source_color, hint_default_black, filter_linear;

// Three representative wavelengths at 680, 550, and 440 nm; optical depths are dimensionless.
const vec3 TAU_R = vec3(5.802e-6, 13.558e-6, 33.1e-6) * 8000.0 * 0.759572;
const vec3 TAU_OZONE = vec3(0.650e-6, 1.881e-6, 0.085e-6) * 15000.0;

void sky() {
    vec3 stars = texture(night_sky, SKY_COORDS).rgb;
    float mu = max(EYEDIR.y, 0.02);
    float mu_sun = max(LIGHT0_DIRECTION.y, 0.03);
    float cosine = clamp(dot(EYEDIR, LIGHT0_DIRECTION), -1.0, 1.0);
    vec3 tau_m = vec3(0.0024 * turbidity / 2.2);
    vec3 tau = TAU_R + tau_m;
    vec3 integral;
    float denominator = 1.0 - mu / mu_sun;
    if (abs(denominator) < 0.001) {
        integral = tau / mu * exp(-tau / mu);
    } else {
        integral = (exp(-tau / mu_sun) - exp(-tau / mu)) / denominator;
    }
    float phase_r = 3.0 / (16.0 * PI) * (1.0 + cosine * cosine);
    float g = 0.76;
    float phase_m = (1.0 - g * g) / (4.0 * PI * pow(1.0 + g * g - 2.0 * g * cosine, 1.5));
    vec3 radiance = max(vec3(0.0), integral * (TAU_R * phase_r + tau_m * phase_m) / tau);
    radiance *= exp(-TAU_OZONE / mu_sun);
    radiance *= 32.0 * LIGHT0_ENERGY;
    radiance /= 1.0 + dot(radiance, vec3(0.2126, 0.7152, 0.0722));
    float disk = smoothstep(cos(LIGHT0_SIZE), cos(LIGHT0_SIZE * 0.5), cosine);
    radiance += disk * LIGHT0_COLOR * LIGHT0_ENERGY * 16.0;
    radiance *= mix(vec3(0.015), vec3(1.0), smoothstep(-0.05, 0.02, EYEDIR.y));
    COLOR = mix(stars, radiance, daylight) * exposure;
}
