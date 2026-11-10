## 2026-03-30 - Upstream denonavr list properties perform expensive deepcopies
**Learning:** Upstream `denonavr` receiver properties such as `netaudio_func_list` and `playing_func_list` call `deepcopy(...)` on their internal lists every time they are accessed. In Home Assistant entity properties that are accessed on every state poll (`supported_features`, `media_image_url`, `media_title`), querying these lists directly causes repeated deepcopy operations and linear scans.
**Action:** Always cache these function lists as sets within entity wrappers and refresh them only when the receiver state is polled (`async_update`).

## 2026-11-10 - Upstream denonavr sound_mode_list is dynamic
**Learning:** In upstream `denonavr`, `receiver.soundmode._sound_mode_map` dynamically grows when new sound modes are reported by the receiver (`match_sound_mode`). Caching `receiver.sound_mode_list` statically at entity initialization causes runtime sound mode discoveries to be omitted from the entity options.
**Action:** Do not freeze `receiver.sound_mode_list` at entity initialization without an invalidation mechanism when new sound modes are discovered.
