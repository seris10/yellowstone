# fixes-14.2 ledger
Doc: fixes/fixes-14.2-weather_http_consumer.gd | read 2026-10-12 | targets: yellowstone_atmosphere/scripts/weather_http_consumer.gd sha256:f93b4d142ed7 ; yellowstone_atmosphere/scripts/yellowstone_atmosphere.gd sha256:63287c1704fa ; yellowstone_midway/scripts/world.gd ; yellowstone_python/yellowstone_python/llm_backend.py
Summary: 8 items: 8 implemented, 0 shortcut, 0 partial, 0 missing, 0 superseded, 0 conflicts

The doc is a proposed replacement file; it has text and a drop-in file. Items are the file's intro bullet list.

| item | requirement (one line) | verdict | evidence file:line | note (one line) | cost cheap/medium/refactor |
|---|---|---|---|---|---|
| 1 | Prevent overlapping HTTP requests | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:90,145-146,159,183 | _request_in_flight guards poll_now, reset in _on_request_completed | cheap |
| 2 | Normalize flat and nested endpoint shapes | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:279-350 | _extract_weather prefers nested, falls back to air_c/humidity/cloud/wind_xz_mps | cheap |
| 3 | Preserve server generated_at_unix and provenance | implemented | yellowstone_midway/scripts/weather_http_consumer.gd:258-268 | snapshot now tags source.client_generated when the server omitted generated_at_unix | cheap |
| 4 | Convert wind vector to meteorological FROM direction | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:446-477 | atan2(-vx, -vz) with +X east / +Z south, fposmod to [0, 360) | cheap |
| 5 | Produce schema_version 1 nested snapshot structure | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:33,258-274 | SCHEMA_VERSION constant, schema_version/generated_at_unix/source/weather/solar fields set | cheap |
| 6 | Atomic snapshot writes | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:554-606 | writes to .tmp, flushes, removes old, rename_absolute | cheap |
| 7 | Reject malformed responses without replacing the last valid file | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:184-221 | empty text, non-200, non-object, and empty normalized all push_warning and return | cheap |
| 8 | Pass normalized weather and solar state to the atmosphere controller | implemented | yellowstone_atmosphere/scripts/weather_http_consumer.gd:223-234 | weather duplicated, solar merged, forwarded through set_weather_state | cheap |

## Cross-project issues
- yellowstone_midway/scripts/world.gd never instantiates YellowstoneWeatherHttpConsumer; even though the live file matches the doc, nothing in the midway build fetches /api/weather.
- The Python /api/weather endpoint in yellowstone_python/yellowstone_python/llm_backend.py:313-321 still ships the pre-fix flat shape (air_c, humidity, cloud, wind_xz_mps), with no server-side generated_at_unix / observed_at_unix / valid_until_unix / nested weather{} block, so the consumer always falls back to the flat path.
- Consumer appends `live_refetch=1` as a required query parameter (line 154-157); the backend handler does not document or require it, so it is a project-local convention that the backend ignores silently.

## Scientific validity flags
- Flat path defaults (DEFAULT_WEATHER lines 46-59, default_cloud_base_agl_m, default_cloud_thickness_m, default_visibility_m) silently fill the required-field check with hard-coded Yellowstone defaults, so a backend that omits visibility, cloud base, or cloud thickness still produces a passing snapshot that is not measured.
- _normalize_weather clamps wind_speed_mps to >= 0 and relative_humidity to [0, 1] without flagging the clamp (lines 374-399); scientific provenance of a negative humidity or negative wind would be lost.
- Default wind_direction_deg of 270 is applied when the backend returns a scalar speed but no direction (lines 361-362 comment, DEFAULT_WEATHER line 51), creating a plausible-looking "measured" westerly that is fabricated.
