# Changelog

## [Unreleased]

### Added
- **Opt-in Espressif AFE audio path** (`base/audio-afe.yaml`, flashed via the new
  `waveshare-va-afe.yaml` thin config), built on
  [esphome-audio-stack](https://github.com/n-IA-hane/esphome-audio-stack)
  `esp_audio_stack` + `esp_afe`, pinned to `v2026.9.1`. One I2S port in 4-slot
  TDM at 48 kHz replaces the two-bus layout; `esp_codec_dev` drives the ES7210
  and ES8311; the two mics and the ES8311's playback reference are captured as
  slots of the same frame, converted to 16 kHz, and run through AEC plus dual-mic
  Speech Enhancement/BSS, noise suppression and VAD. micro_wake_word and
  voice_assistant consume the processed stream, **so the wake word keeps working
  while music or TTS is playing** - the barge-in that the stock path cannot do.
  No forked ESPHome components are used. Requires ESPHome 2026.6.5+.
  **Not yet confirmed on hardware.**
- **New entities on the AFE path only**: `Master Volume`, `Echo Cancellation`,
  `Voice Activity Detector`, `Voice Detected`, and four `TDM slot N level`
  diagnostic sensors for resolving the slot map on a real board.

### Changed
- **The TDM slot map is confirmed on hardware**: slot 0 and slot 2 are the
  microphones, **slot 1 is the playback reference**, slot 3 is unused. This
  matches the esphome-intercom reference config and contradicts the schematic
  reading, the Waveshare demo's `"RMNM"` and esphome-audio-stack's own Korvo-2
  baseline table, all of which put the reference elsewhere. `docs/HARDWARE.md`
  records the measurements.
- **Post-AFE mic gain defaults to 15 dB on first boot.** The component's
  `mic_gain` number has no `initial_value` in its schema (it restores from flash
  or sits at 0 dB), so `base/audio-afe.yaml` applies `mic_gain_default` once from
  `on_boot`, guarded by a restored global; a value set later in HA persists and
  is never overridden.
- **`hey_mycroft` is now the default wake word; `alexa` ships disabled.**
  micro_wake_word enables only the first model in the list, so `alexa` is now
  second: present and selectable from the "Wake word" entity in Home Assistant
  (persisted across reboots), but holding no memory until you enable it. A
  disabled model's tensor arenas are deallocated by `unload_model()` and
  reloaded lazily, so the cost while off is flash only. **This affects both
  audio paths.**
- **Media player volume clamps default to `0.2` / `0.6`** (were `0.4` / `0.8`).
  On the AFE path this means the signal is scaled both by the media player and
  by the codec curve (`master_volume_min_db`); open the clamps to `0.0`/`1.0` if
  the bottom of the range feels dead.
- **`min_version` moved from `base/core.yaml` into the audio path packages**
  (2025.8.0 in `base/audio-stock.yaml`, 2026.6.5 in `base/audio-afe.yaml`). It
  cannot be a substitution: the remote-package loader parses
  `esphome.min_version` off the raw YAML and version-parses it before
  substitutions are applied, so `${...}` there fails with `Not a valid version
  number`. Local `!include` packages skip that loader, which is why it only
  shows up once the file is fetched by `url:`/`ref:`.
- **`base/core.yaml` no longer contains any audio hardware.** It was split so the
  two paths can share one LED state machine, timer/alarm engine, button set and
  entity list - switching paths does not recreate Home Assistant entities. The
  stock hardware layer moved verbatim into `base/audio-stock.yaml`, and thin
  configs now list both files in `packages:`. The resolved stock configuration is
  unchanged: `esphome config` output differs only by five new substitution
  declarations and the order of the `number:` block.
- **`scripts/validate.py` also reports duplicate top-level keys.** PyYAML keeps
  only one of them, so a second `esphome:` block in a file silently discards
  everything in the losing copy with no error anywhere - it just goes missing
  from the compiled config.
- **`scripts/validate.py` accepts comma-separated file groups**, validating
  `core.yaml` plus one audio package as one merged config, since neither half
  resolves standalone any more.
- **The AFE path renames the mic-gain entity to `Mic gain (digital)`.** Stock's
  `Mic gain (ES7210)` is the ES7210's analog PGA (0 to 37.5 dB); on the AFE path
  that gain is compile-time (it also feeds the echo reference, so it is not safe
  as a live control) and the runtime entity is digital trim after the AFE
  (-20 to +30 dB). The stock entity is untouched.
- **The AFE path shapes loudness with the codec curve** (`master_volume_min_db`
  at -30 dB, since `esp_codec_dev`'s ~-50 dB default drops away far too fast on
  this board's ES8311/NS4150 path) and opens the media player's
  `volume_min`/`volume_max` to 0.0/1.0, so the signal is not scaled twice.
- **The AFE path powers the amplifier down 30 s after playback stops.** The stock
  path can leave PA_EN on forever because its i2s speaker holds the line at clean
  silence (`timeout: never`); `esp_audio_stack` tears the speaker path down, so a
  still-enabled amp would amplify an undriven DAC line as hiss.
- **The AFE path defaults to `logger: level: INFO`**, because per-frame logging on
  the audio core is itself enough to glitch the audio.
- **The boot chime's ordering constraint is now a substitution**
  (`boot_chime_delay`, 1 s on stock, 0 s on AFE). It existed only because the
  stock speaker is slaved to the mic's I2S clock.

### Documentation
- **`docs/HARDWARE.md`**: the ES7210 TDM slot map now has its own section. Four
  sources give three different answers - the schematic read (ref on slot 2),
  Waveshare's demo `"RMNM"` (slot 0), esphome-audio-stack's Korvo-2 baseline
  table (slot 2) and esphome-intercom's measured map for this exact board
  (slot 1, mics on 0 and 2), the last two being the same author contradicting
  himself. The firmware defaults to the measured map and ships slot-level sensors
  to settle it per board. The "hardware AEC is not usable here" claim is now
  scoped to the stock path, which is all it was ever true of.
- **`README.md`**: an Audio paths section comparing the two, how to opt in, and
  what changes.
- **`docs/AFE-BRINGUP.md`** (new): the hardware checklist for the AFE path -
  confirming the slot map with the level sensors first, then wake word over
  music, barge-in, STT comparison, mute, amp/chime behaviour, volume range and
  heap headroom - plus a symptom-to-substitution table.
- **`skill/waveshare-esp32-s3-audio/SKILL.md`**: an AFE section with the gotchas
  found building it - `mic_selected: 0x0F` or the reference slot reads zeros; a
  silent reference warns but a wrong-but-live one does not; `gain_db` amplifies
  the reference too; feed and fetch tasks must be on different cores; and the two
  YAML traps (a substitution cannot hold a list, and `[${a}, ${b}]` is a parse
  error because `${` opens a flow mapping).

## [1.0.0] - 2026-07-18

First stable release. The full voice assistant is confirmed on hardware, the
regressions found during bring-up testing are fixed, and the project ships with
complete documentation and a wiki. Tagged `v1.0.0`; the example config pins this
tag so a build is reproducible instead of tracking a moving `main`.

### Fixed
- **Boot loop into safe mode after selecting a ring effect.** The three
  effect selects restore their saved option during `setup()` (at HARDWARE
  priority), which fired `on_value` and ran the LED state machine before the
  light/RMT and voice_assistant were initialised, painting an effect on an
  uninitialised strip and crashing the boot. The `on_value` is now gated on
  `init_in_progress` (cleared by `on_boot` at priority -100), so it only runs
  once setup is complete; a live effect change from HA still repaints the ring.

### Changed
- **Boot chime is now a bundled sound, not the wake-word beep.**
  `base/sounds/startup.mp3` (16 kHz mono, ~11 KB) plays on connect to HA and is
  swappable through the `boot_sound_file` substitution (any URL or local
  MP3/FLAC/WAV; the media player decodes all three).

### Removed
- **The Flicker ring effect** (weak visually); 15 effects remain.

## [0.2.0] - 2026-07-18

First on-hardware bring-up. The full voice assistant works: on-device wake word,
STT/intent/TTS, clean playback, no boot hiss - all on stock ESPHome components.

### Changed
- **Audio reworked to two I2S buses with the mic as master; the patched es8311
  and `force_master` are gone.** The board shares BCLK/LRCLK between the DAC and
  ADC, and ESPHome can't run one bus full-duplex (the speaker hits "Parent bus
  is busy"). Two buses over the shared pins, with the always-capturing mic
  mastering the clock and the speaker slaving to it, gives simultaneous capture
  and playback on stock components. The mic is pinned to 16-bit so its master
  frame matches the DAC (a 32-bit frame played back as noise).
- **The amplifier is gated on playback** (`ALWAYS_OFF` at boot, turned on by the
  media_player `on_state`) to remove the idle hiss the always-on amp produced
  before the first playback.
- **API encryption dropped** (LAN-only device); `secrets.yaml` is now just Wi-Fi.
  Re-enable it via the commented block in `base/core.yaml` if you want it.
- **Timers are visible in HA** (the "Next timer" / "Next timer name" sensors are
  no longer `disabled_by_default`).
- **Boot chime**: a short "ready" sound plays once the device connects to HA,
  played after the mic (I2S master) is clocking so the slave speaker can output
  it. New `boot_sound` switch toggles it. The sound ships with the repo
  (`base/sounds/startup.mp3`, 16 kHz mono) and is swappable via the
  `boot_sound_file` substitution (any URL or local MP3/FLAC/WAV).

### Added
- **Per-phase ring animation, pickable from HA.** New "Listening effect",
  "Thinking effect" and "Replying effect" selects choose the animation for those
  voice-assistant phases (the phase colour stays fixed). 15 effects to choose
  from: solid, three pulses, Breathe, Wipe, Scan, Spinner, Comet, Twinkle,
  Random Twinkle, Fireworks, Fire, and two rainbows. Breathe / Spinner /
  Comet / Fire are custom `addressable_lambda` effects.

### Fixed
- **The Pulse LED effects showed a solid colour instead of pulsing.** Their
  `update_interval` (16 ms) was shorter than the transition (300-1000 ms);
  `update_interval` is how often the pulse flips its brightness target, so it
  flipped faster than the brightness could move. Now ~2x the transition, with
  30-100% min/max brightness.
- Compile-time issues found during bring-up: a quoted `mclk_multiple`
  substitution (string vs the int a `cv.one_of` wants), a `template select`
  missing its `options:`, `select` `.state` -> `current_option()`, the dead
  microWakeWord model URLs (404), and a `/` in a switch name.

### Removed
- **The `stop` wake word.** This board has no usable hardware AEC, so the mic
  hears the device's own TTS far louder than the user; "stop" is detected only
  weakly and too late to be useful.
- **The daily-alarm entities** (Alarm time / Alarm on / Alarm action), the
  device-clock text sensor, and the diagnostic mic-disable switch are now
  `internal:` (hidden from HA). The logic stays; the clutter is gone.
- The dead "Mute and unmute sound" switch and its unused sound files.
- `components/es8311/` and the `external_components:` block - no longer needed.

## [0.1.0] - 2026-07-17

First cut. A working single-file config for the Waveshare ESP32-S3-AUDIO-Board,
restructured into a core package + a thin user config, with the patched
`es8311` component brought in-tree so nothing depends on an upstream repo that
has gone quiet.

### Added
- `base/core.yaml`: the always-on core with ES8311 speaker, ES7210 dual mic,
  on-device wake word (`alexa` + `okay_nabu`), the HA Assist pipeline,
  music/announcement mixing with ducking, the 7x WS2812 status ring state
  machine, the three onboard buttons, voice timers and an alarm clock.
- `waveshare-va.yaml`: thin user config. Pulls the core from GitHub at compile
  time, so it is the only file you keep.
- `components/es8311/`: vendored fork of ESPHome's `es8311` adding
  `force_master` + `mclk_multiple`. Origin, credits and the licensing situation
  are in the README.
- `docs/HARDWARE.md`: board pinout and the I2C device map.
- `skill/waveshare-esp32-s3-audio/`: Claude Code skill with pinout + gotchas.
- `scripts/validate.py`: offline YAML check (syntax, substitutions, duplicate
  ids) so a typo does not cost a dashboard round trip.
- `scripts/esplog.py`: stream device logs over the native API.

### Fixed
Bugs carried over from the config this started as:

- **The mic was stopped on every boot.** The `diag_disable_mic` check was
  inverted: with the switch in its default OFF position `on_boot` ran
  `micro_wake_word.stop` + `microphone.stop_capture`. It only ever recovered
  because `on_client_connected` restarted the wake word, so the switch also did
  not actually work, in either direction.
- **"Microphone Mute" did not mute.** It dropped the ES7210 gain to `0.0f`,
  but 0 dB is *unity* gain, not silence. The mic kept hearing the room and only
  the wake-word handler ignored it. It now uses ESPHome's own `microphone.mute`,
  which hands every consumer a zero-filled buffer, so the wake word hears actual
  silence with no I2S restart.
- **A test sound fired on every LED repaint during boot.** A leftover
  `id(play_sound).execute(1, id(wake_word_triggered_sound)); //TEST` sat in the
  `init_in_progress` branch of `control_leds`.
- **Wake word sensitivity did nothing.** The select only set cutoffs on
  `okay_nabu`, while the primary wake word is `alexa`. It now sets both.
- **Mic gain slider promised 42 dB.** The ES7210 caps at 37.5 dB and the driver
  silently clamps, so the top third of the slider was a lie. Range is now
  0 to 37.5 dB in 1.5 dB steps (the chip's real granularity), and the boot value
  in `audio_adc` matches the number entity instead of contradicting it (24 dB vs
  a 32 dB global).
- **The API encryption key was hard-coded in the config.** It now comes from
  `!secret api_encryption_key`.
- **The `time:` block was half-commented-out**, leaving `id: rtc` dangling under
  `platform: homeassistant`. Cleaned up. PCF85063 support is not in this build.
- **Two `on_boot: priority: -100` blocks** ran in an order nobody had chosen.
  Merged into one.

### Changed
- All pins, audio format and the HA-facing values are `substitutions:` with
  documented defaults, instead of literals scattered through the file.
- `${mic_channel_${which_mic}}` nested-substitution trickery replaced with two
  plainly named knobs: `mic_channel` (the I2S slot) and `mic_va_channel` (the
  index handed to Assist). These are genuinely different things and the old
  names implied they were the same one.
- Dropped dead substitutions (`i2s_bits_per_sample`, `i2s_mode_speaker`,
  `rtc_int`, `mic_channel_2`) and the now-unused `mic_gain_saved` global.
- Timezone is a `posix_timezone` substitution rather than a hard-coded `UTC0`.
