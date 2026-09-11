---
name: waveshare-esp32-s3-audio
description: >
  Reference for building/editing ESPHome configs on the Waveshare
  ESP32-S3-AUDIO-Board (ESP32-S3R8 smart-speaker devkit: ES8311 codec + NS4150B amp,
  ES7210 dual-mic ADC, TCA9555 I/O expander, 7x WS2812 ring, PCF85063 RTC, DVP camera
  and SPI LCD connectors). Use whenever working on this board (or the base/*.yaml in
  this repo): correct pinout, the two audio paths (stock two-bus i2s_audio vs the
  opt-in esp_audio_stack/esp_afe TDM path) and the contested TDM slot map, the
  mute/gain traps, the EXIO map, strapping pins, and which "official" sources are wrong.
---

# Waveshare ESP32-S3-AUDIO-Board: ESPHome working notes

Facts below are from Waveshare's **schematic v1.1** and their **own demo source**
(Arduino + ESP-IDF), cross-checked with a working ESPHome config. Where sources
conflict, that is stated. Don't paper over it.

Full detail and citations: `docs/HARDWARE.md` in this repo.

## Board

- **ESP32-S3R8** (bare chip), 240 MHz, **8 MB octal PSRAM**, **16 MB flash**.
- **ES8311** mono codec (DAC) into **NS4150B** Class-D amp into speaker (JST header).
- **ES7210** 4-ch ADC with **2 physical mics** (CH1/CH2). CH3 = AEC loopback per
  the schematic, but the **TDM slot** it lands on is contested - see the AFE section.
- **TCA9555** I/O expander @ 0x20: amp enable + 3 buttons (+ LCD/cam/SD lines).
- **7x WS2812B** ring on GPIO38, driven directly over RMT, **not** via expander.
- **PCF85063** RTC @ 0x51. DVP camera + SPI/QSPI LCD connectors. USB-C. Li-ion header.
- Wi-Fi 2.4 GHz + BT 5 LE. ESP32-S3 has **no Bluetooth Classic**, so no A2DP.

ESPHome target: `board: esp32-s3-devkitc-1`, `variant: esp32s3`, `flash_size: 16MB`,
`framework: esp-idf`, `psram: {mode: octal, speed: 80MHz}`.

## Pinout (authoritative)

```
I2S (ONE shared bus):  MCLK=12  BCLK/SCLK=13  LRCK/WS=14   DIN=15 (mic)  DOUT=16 (spk)
I2C (one bus):         SDA=11   SCL=10        100 kHz confirmed working
LED ring WS2812:       DATA=38  (7 LEDs, RGB order, but verify: see gotchas)
BOOT button:           GPIO0 (active low).  RESET = hardware CHIP_PU, not readable.
SD (1-bit SDMMC):      CLK=40 CMD=42 D0=41   CS=EXIO3   (D1/D2 = NC)
LCD (use WIKI table):  CS=3 SCK=4 BL=5 SDA3=6 DC=7 MISO=8 MOSI=9  RST=EXIO0
Camera DVP:            D0=2 D1=17 D2=18 D3=39 D4=45 D5=46 D6=47 D7=48
                       VSYNC=21 HREF=1  PCLK/XCLK muxed 44/43 or 19/20  PWDN=EXIO5
USB:                   D-=19  D+=20        UART0: TX=43 RX=44
GPIO33-37:             UNUSABLE, taken by octal PSRAM (flash uses 26-32)
```

I2C addresses: **ES8311 0x18**, **ES7210 0x40**, **TCA9555 0x20**, **PCF85063 0x51**.

### TCA9555 EXIO map

```
0: LCD_RST     4: unknown          8:  PA_EN  (amp enable, ACTIVE HIGH)
1: TP_RST      5: CAM_PWDN (AL)    9:  Key1   (active low, 10k HW pull-up)
2: TP_INT      6: Camera_SEL  *    10: Key2   (active low)
3: SD_CS       7: USB/cam mux *    11: Key3   (active low)
                                   12-15: expansion header
* EXIO6/EXIO7: schematic and wiki/demo disagree on which does the mux.
  NEVER drive either. The wrong one kills USB and forces manual download mode.
```

The TCA9555 has **no reset pin** (schematic pin 1 is `INT#`).

## The one thing that defines this board: shared I2S clocks

ES8311 and ES7210 sit on the **same BCLK (13) / LRCK (14)**. Only one device may
drive them, and **ESPHome cannot run a single i2s_audio bus full-duplex**: a
microphone and a speaker on one bus each call `i2s_new_channel` on the port, and
the second fails at runtime with `Parent bus is busy` (the speaker then crackles).

The layout that works on **stock ESPHome** (no patched es8311):

- **Two i2s_audio buses** (two I2S ports) over the shared pins. The **mic bus is
  the master** and the **speaker bus is a slave** reading its clock.
- The mic is always capturing for the wake word, so as master it drives
  BCLK/LRCK/MCLK **continuously** - which is what a slave speaker (and the ES8311
  DAC) need. Making the mic the master also gives it a correct-rate stream; a
  codec-mastered clock (the old `force_master` route) fed the mic garbage and
  killed wake word.
- **Pin the mic to 16-bit.** As master it sets the frame slot width, and the
  i2s_audio default is 32-bit; a 32-bit frame against the 16-bit ES8311/speaker
  doubles the bit clock they expect and playback comes out as noise.

```yaml
i2s_audio:
  - id: i2s_input                 # mic bus = master (drives the shared clock)
    i2s_mclk_pin: GPIO12
    i2s_bclk_pin:  { number: GPIO13, allow_other_uses: true }
    i2s_lrclk_pin: { number: GPIO14, allow_other_uses: true }
  - id: i2s_output                # speaker bus = slave
    i2s_bclk_pin:  { number: GPIO13, allow_other_uses: true }
    i2s_lrclk_pin: { number: GPIO14, allow_other_uses: true }
audio_dac:   { platform: es8311, id: es8311_dac }   # stock
audio_adc:   { platform: es7210, id: adc_mic }      # stock
microphone:
  - platform: i2s_audio
    i2s_audio_id: i2s_input       # default i2s_mode: primary -> master
    bits_per_sample: 16bit
speaker:
  - platform: i2s_audio
    i2s_audio_id: i2s_output
    i2s_mode: secondary           # slave to the mic's clock
```

Do **not** make the ES8311 the master via a `force_master`-style patch: a
codec-mastered clock feeds the ESP mic a wrong-rate stream and kills the wake
word. The ESP-mastered two-bus layout needs no patched component.

## Gotchas that cost real time

- **`microphone.mute` is the correct mute.** It makes the Microphone hand every
  consumer a zero-filled buffer (`set_mute_state` in `microphone.h`), so the wake
  word hears real silence and the stream never restarts. **Do not "mute" by
  setting ES7210 gain to 0**, because 0 dB is *unity* gain, not silence. There
  are also `microphone.unmute` and the `microphone.is_muted` condition.
- **ES7210 gain caps at 37.5 dB**, not 42. `set_mic_gain()` does
  `clamp<float>(gain, MIN, MAX)` and the register steps are 3 dB up to 33 dB,
  then 34.5/36/37.5. A slider promising more than 37.5 is lying to the user.
- **Template switch triggers fire during `setup()`**, at `setup_priority
  HARDWARE - 2`, i.e. **before** the mic/mWW components exist, whenever
  `restore_mode` isn't `DISABLED` (`TemplateSwitch::setup()` calls
  `turn_on()`/`turn_off()`, which fires the trigger). If a switch's
  `on_turn_on`/`turn_on_action` touches audio components, guard it with an
  `init_in_progress`-style flag and apply the real state from `on_boot`
  (priority -100). **The same applies to a template `select` with
  `restore_value: true`**: it replays the saved option during `setup()` and
  fires `on_value` before the light/RMT and voice_assistant exist. An
  `on_value` that repaints the ring (`control_leds`) then paints an effect on
  an uninitialised strip and crash-loops the board into safe mode. Guard the
  `on_value` with the same `init_in_progress` check.
- **`channels:` on `voice_assistant`/`micro_wake_word` is NOT a channel count.**
  If you wrap the mic (`microphone: { microphone: id, channels: N }`) it is a
  `MicrophoneSource` and `channels` is a **list of channel indices**
  (`cv.ensure_list(cv.int_range(0, 7))`, default `0`), not a count. This firmware
  just passes the mic directly (`microphone: i2s_mics`) and lets it default, so
  the wrapper isn't used - simplest, and Assist won't take a stereo source anyway.
- **Hardware AEC is not reachable from *stock* ESPHome here.** The demo packs
  4x16-bit ADC channels into 2x32-bit I2S slots and unpacks in software;
  `i2s_audio` doesn't. On the stock path use `noise_suppression_level` /
  `auto_gain` and accept the fallout: the mic hears the device's own speaker
  loudly, so a "stop" wake word to interrupt a reply does not work (detected too
  weakly and late). **It IS reachable via `esp_audio_stack` + `esp_afe`**
  (esphome-audio-stack), which is what `base/audio-afe.yaml` does - see the AFE
  section below.
- **Cold-boot: mic + LEDs sometimes don't come up until a reset.** Reported on
  the HA forum in **a single post with zero replies, with no published root cause
  or fix.** The TCA9555 direction registers defaulting to `0xFF` (all inputs)
  would leave PA_EN undriven, which ESPHome's `tca9555` + a `RESTORE_DEFAULT_ON`
  GPIO switch on EXIO8 addresses. But that does **not** explain the LED symptom
  (the ring is on GPIO38/RMT, not the expander), and the reporter says replaying
  registers didn't help. Don't claim this is solved.
- **Strapping: GPIO45 (CAM_D4) and GPIO46 (CAM_D5) must be LOW at boot.** A
  camera left plugged into J3 sits on both and can stop the board booting, even
  on a voice-only build. GPIO3 (LCD_CS) is also a strap, so don't add strong
  pulls.
- **Waveshare's demo source contains stale copy-paste from other boards.** Proven:
  its `bsp_board.h` LCD pins contradict the wiki's LCD table, and its
  `BAT_ADC_PIN 8` contradicts the schematic's GPIO1 (GPIO8 is LCD_MISO here).
  **Prefer the wiki + schematic over the demo for pin tables**; prefer the demo
  for *behaviour* (which EXIO gets driven, init order).
- **The HA forum thread swaps I2C**: it says SDA=10/SCL=11. It's SDA=11, SCL=10.
- **RGB vs GRB**: the demo says RGB and its own trailing comment says GRB, while
  WS2812B is conventionally GRB. Two sources favour `rgb_order: RGB`, but
  confirm with a pure-red test before trusting either.
- **Idle-amp hiss at boot.** The amp (PA_EN on EXIO8) enabled at boot amplifies
  the undriven DAC line as a faint hiss until the first playback (after which the
  i2s speaker, `timeout: never`, holds the line at clean silence). Fix by gating
  the amp: `restore_mode: ALWAYS_OFF`, then turn it on from the media_player
  `on_state` when playback starts and leave it on. **Do not** try to fix this by
  playing a boot sound through the media player - a standalone boot announcement
  leaves `media_player.is_announcing` stuck true, and `on_wake_word_detected`
  then only ever stops that phantom announcement instead of starting Assist
  (wake word detected, nothing happens).
- **Battery monitoring is effectively unavailable**: the divider needs a 0 Ω
  resistor soldered (depopulated by default) and **enabling it kills the camera**.
  Ratio 3.0. Pin is GPIO1 per schematic, not GPIO8, which is stale demo code.

## The opt-in AFE path (esp_audio_stack + esp_afe)

`base/audio-afe.yaml` replaces the whole hardware layer - `i2s_audio`, `es7210`,
`es8311` and the hardware speaker sink all go away - with one `esp_audio_stack`
that owns a single 48 kHz TDM bus, drives both codecs through `esp_codec_dev`,
converts only the mic/reference path down to 16 kHz, and feeds `esp_afe`. The
stock path stays the default in `base/audio-stock.yaml`. `base/core.yaml` is
shared and holds no audio hardware at all.

Gotchas specific to that path:

- **The TDM slot map is contested, and four sources give three answers.** The
  schematic says MIC3 is the AEC loopback (ref on slot 2); the Waveshare demo
  declares `"RMNM"` (ref on slot 0); esphome-audio-stack's own bring-up table
  files this board under the Korvo-2 baseline (`tdm_ref_slot: 2`); and
  esphome-intercom's config *for this exact board* says slot 0 = right mic,
  slot 2 = left mic, **slot 1 = playback reference**. Note the last two are the
  same author contradicting himself. **The last one is correct** - confirmed on
  hardware in this repo with the `TDM slot N level` sensors, so the schematic
  reading and the Korvo-2 baseline table are both wrong for this board.
  Two tells when checking a board: the two mic slots track each other within
  about a decibel under speech, and the reference slot has a *lower* idle noise
  floor than either mic (an electrical DAC tap has no capsule self-noise).
  Discriminate with **speech and playback stopped** - during playback the mics
  hear the speaker too, so every slot rises and the test proves nothing.
- **`mic_selected: 0x0F` is mandatory.** The ES7210 otherwise leaves ADC3/ADC4
  clocked off and the reference slot reads zeros. In `esp_audio_stack` this is
  `codec.input.mic_selected`, which reaches the `esp_codec_dev` ES7210 driver; it
  replaces the raw register pokes older configs did by hand.
- **The `TDM AEC reference silent` warning does not exist in the shipped
  component.** Its README documents it, but the code is behind
  `USE_ESP_AUDIO_STACK_TDM_REF_DIAGNOSTIC`, which nothing ever defines and which
  has no YAML option - verify with
  `grep -rn TDM_REF_DIAGNOSTIC` and by checking the build's `defines.h`. So a
  wrong `tdm_ref_slot` is **completely silent**, whether the slot is dead or
  pointed at a live microphone. The `TDM slot N level` sensors on the
  `esp_audio_stack` sensor platform are the only working instrument; read them
  as a delta under stimulus, never at idle.
- **`codec.input.gain_db` hits the reference slot too.** The analog PGA applies
  to every selected channel, so cranking it to help the mics also amplifies the
  loopback. Trim the reference separately with `ref_channel` / `ref_gain_db`
  rather than lowering the shared gain.
- **The mic-gain entity changes meaning.** Stock exposes the ES7210's analog PGA
  (0 to 37.5 dB) via `es7210.set_mic_gain()`. On the AFE path the analog gain is
  compile-time and the runtime `mic_gain` number is *digital trim after the AFE*
  (-20 to +30 dB). Don't present them as the same control.
- **Don't clamp volume twice.** The AFE path shapes loudness with
  `master_volume_min_db` (-30 dB suits this board's ES8311/NS4150; the
  `esp_codec_dev` default near -50 dB drops away far too fast) plus a
  `master_volume` number. The media player's own `volume_min`/`volume_max` then
  have to be opened to 0.0/1.0, or the signal is scaled in both places.
- **The amp must now be powered down when idle.** The stock path can leave PA_EN
  on forever because its i2s speaker has `timeout: never` and holds the line at
  clean silence. `esp_audio_stack` tears the speaker path down, so an amp left
  enabled amplifies an undriven DAC line as hiss. Use
  `on_amplifier_required` / `on_amplifier_idle` with a restartable delay long
  enough to cover back-to-back sounds (30 s), not an immediate turn-off, or every
  sound clicks.
- **Keep the hardware sink's `buffer_duration` short** (128 ms, not the 500 ms
  default). The ESPHome mixer pushes 50 ms chunks every 25 ms; a long backlog at
  the sink delays backpressure reaching the media/TTS decoders.
- **`logger: level: DEBUG` can itself glitch the audio.** Per-frame logging on
  the audio core is enough to cause dropouts; run the AFE path at INFO.
- **AFE feed and fetch tasks must be pinned to different cores** - the validator
  enforces it, and Espressif's own GMF guidance is that sharing a core invites an
  AFE task watchdog. The qualified layout on this board is audio stack on core 1
  at priority 19, feed on core 0, fetch on core 1.
- **AGC off, SE/NS not runtime-switchable on dual mic.** `se_enabled` is
  structural: turning it off makes esp-sr fall back to first-mic-only. NS isn't
  worth exposing either, because `afe_config_check()` prioritises SE/BSS over NS
  for two-channel input. AGC can help wake word under playback but causes
  TTS/media stutter on this board and needs a full AFE rebuild to toggle.
- **YAML mechanics that cost time here:** a substitution cannot carry a list, so
  `tdm_mic_slots` needs one substitution per slot; and `[${a}, ${b}]` is a YAML
  parse error because `${` opens a flow mapping inside a flow sequence - use the
  block sequence form.
- **`esphome: min_version:` can NEVER be a substitution in a file loaded as a
  remote package.** The package loader reads `esphome.min_version` straight off
  the raw YAML and runs `cv.Version.parse` on it *before* the substitution pass
  (`esphome/components/packages/__init__.py`, the `_load_package_yaml` helper),
  so `min_version: ${foo}` dies with
  `ValueError: Not a valid version number ${foo}`. Put a literal in whichever
  package file actually needs the floor - here `base/audio-stock.yaml` declares
  2025.8.0 and `base/audio-afe.yaml` declares 2026.6.5, and the `esphome:` blocks
  merge. **This is also a testing trap:** local `packages: {x: !include f.yaml}`
  does not go through that loader, so a `${...}` min_version validates fine
  locally and only fails once the file is pulled by `url:`/`ref:`. Validate
  package changes through a real remote package - a `file://` URL pointing at a
  local git clone is enough.
- **No forks needed.** esphome-intercom's reference config pulls forked
  `speaker`, `voice_assistant`, `ota` and `audio_http`, but their own
  `UPSTREAM.md` files show the patches are additive opt-ins that preserve
  upstream defaults (`pause_releases_pipeline`, `tts_playback_start_timeout`) or
  serve VoIP/simulator needs. Upstream ESPHome components work. In particular
  `ESPAudioStackMicrophone` derives from `microphone::Microphone` and honours
  `mute_state_` by zero-filling, so `microphone.mute` behaves exactly as on the
  stock path.

## Validating without flashing

ESPHome is the real validator, but `scripts/validate.py` in this repo catches
YAML syntax, unresolved `${substitutions}` and duplicate component ids offline.
Note when writing such tooling: an `id:` under a **dotted key** (`script.execute`,
`light.turn_on`, `mixer_speaker.apply_ducking`) is a *reference*, not a
declaration. Component declarations never sit under a dotted key.

`scripts/esplog.py` streams device logs over the native API (reads the API key
out of `secrets.yaml`), which beats the dashboard's log view for boot-time races.
