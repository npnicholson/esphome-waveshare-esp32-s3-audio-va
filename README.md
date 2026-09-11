![ESPHome and Home Assistant voice assistant on the Waveshare ESP32-S3-AUDIO-Board](docs/hero.jpg)

# ESPHome Voice Assistant for the Waveshare ESP32-S3-AUDIO-Board

A **Home Assistant voice satellite** running on the
[Waveshare ESP32-S3-AUDIO-Board](https://www.waveshare.com/esp32-s3-audio-board.htm),
the little AI smart-speaker devkit with a dual-mic array, an ES8311 codec, three
buttons and a 7-LED RGB ring. Pure ESPHome, no custom C firmware: an always-on
core you pull as a package, plus one thin config file you actually edit.

<div align="center">
  <video src="https://github.com/user-attachments/assets/0eae0230-de47-4f20-a6ea-47f65af35f86" controls width="400"></video>
</div>

> **Status: stable (v1.1.0).** Wake word, STT/TTS, clean playback and the LED
> ring are confirmed on-device on both audio paths - including the opt-in
> Espressif AFE path, where the wake word keeps working over music and during a
> TTS reply. Full docs are in the
> [Wiki](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki);
> the release history is in [CHANGELOG.md](CHANGELOG.md).

```
You  ──▶  Waveshare ESP32-S3  ──▶  Home Assistant Assist
         (wake word + audio)      (STT / LLM / TTS)
```

> [!TIP]
> ⭐ **Enjoying this project?** Every star is real motivation to keep it going.
>
> [![Star this repo](https://img.shields.io/github/stars/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va?style=social)](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va)

## What it does

![Home Assistant entities, the LED ring animation picker, the media player and the wake-word controls](docs/features.jpg)

- **Voice assistant**: on-device wake word (`hey_mycroft` by default, with
  `alexa` shipped disabled and switchable from HA) via
  `micro_wake_word`, the full Home Assistant Assist pipeline (STT / LLM / TTS),
  a wake beep and music ducking while it listens.
- **Simultaneous music and announcements**: a mixer speaker blends the media and
  announcement pipelines, so a doorbell announcement ducks the music instead of
  fighting it. Both are exposed to Music Assistant.
- **LED ring**: one state machine drives it. Boot, no-Wi-Fi, no-HA, listening,
  thinking, replying, timer counting, ringing, volume changed - each a distinct
  colour/effect. Brightness and the animation for the listening / thinking /
  replying phases are pickable from HA: solid plus 14 animations - pulses,
  breathe, wipe, scan, spinner, comet, twinkle, fireworks, fire, rainbows.
- **Timers**: set by voice, with an on-ring countdown and a "Next timer" sensor
  in HA. (A daily-alarm engine is present but its entities are hidden by default.)
- **Buttons**: the three onboard keys do volume down, play-pause, volume up.
- **Boot chime**: a short "ready" sound once the device connects to HA
  (toggleable, and it also settles the amp so the ring boots silent).
- **Tunable live from HA**: microphone mute, mic gain, LED brightness and
  wake-word sensitivity are all entities, so there's no reflashing to tune it.
- **Two audio paths, one core**: the default stock-ESPHome path, or an opt-in
  Espressif AFE path with echo cancellation so the wake word keeps working over
  music and TTS. See [Audio paths](#audio-paths).

## Quick start

> Requires **ESPHome 2025.8.0+** on the stock path, **2026.6.5+** on the AFE path.

1. Copy `secrets.example.yaml` to `secrets.yaml` and fill in your Wi-Fi. The
   native API is unencrypted by default; enable encryption in `base/core.yaml`
   if you want it (see the commented block there).
2. Copy **`waveshare-va.yaml`** next to it and edit the `substitutions:` at the
   top (device name, timezone, volume limits). That thin file is the only
   firmware file you keep. The core is **pulled from GitHub at compile time**,
   see its `packages:` block. (For echo cancellation, copy
   **`waveshare-va-afe.yaml`** instead - see [Audio paths](#audio-paths).)
3. **First flash over USB**, then updates go wireless:
   ```
   esphome run waveshare-va.yaml
   ```
   Or drop both files into the ESPHome dashboard's `/config/esphome/` and hit
   Install.
4. In Home Assistant: the new ESPHome device appears, open **Configure** and
   assign an Assist pipeline.
5. Say "Hey Mycroft". The ring should go violet.

Both example configs pin the `v1.1.0` release tag (`ref:` in the `packages:`
block), so a build is reproducible. To move to a newer release, bump `ref:` to a
later tag - or set it to `main` to track the latest changes, accepting that they
can move under you. After changing `ref:`, run `esphome clean waveshare-va.yaml`
(clears the package cache) and then `esphome run waveshare-va.yaml`.

## Documentation

The [Wiki](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki)
has the full guide:

- **[Installation](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/Installation)**: first flash, Home Assistant setup, updating.
- **[Configuration](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/Configuration)**: every substitution and every Home Assistant entity.
- **[Audio architecture](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/Audio-architecture)**: the shared-I2S two-bus design, in depth.
- **[LED ring](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/LED-ring)**: the state machine and every ring effect.
- **[Hardware](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/Hardware)**: pinout, I2C map, and sourced gotchas.
- **[Troubleshooting](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/Troubleshooting)** and **[FAQ](https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va/wiki/FAQ)**.

## Audio paths

The firmware ships **two** audio hardware layers. `base/core.yaml` holds
everything else - the LED state machine, timers, alarm, buttons, entity names
and ids - so switching paths does not recreate your Home Assistant entities.
Pick one by choosing which thin config you flash.

| | **Stock** (default) | **AFE** (opt-in) |
|---|---|---|
| Thin config | `waveshare-va.yaml` | `waveshare-va-afe.yaml` |
| Package | `base/audio-stock.yaml` | `base/audio-afe.yaml` |
| Components | stock ESPHome `i2s_audio`, `es7210`, `es8311` | [esphome-audio-stack](https://github.com/n-IA-hane/esphome-audio-stack) `esp_audio_stack` + `esp_afe` |
| Bus | two I2S ports over the shared pins, 16 kHz | one I2S port, 4-slot TDM, 48 kHz, mic path converted to 16 kHz |
| Echo cancellation | none | AEC against the ES7210's hardware playback-reference slot |
| Mics used | **one** channel (`channel: right`) | **both**, combined by Speech Enhancement/BSS into one clean stream |
| Wake word over music/TTS | unreliable - the mic hears the speaker | works; this is the point |
| Confirmed on hardware | yes, since v0.2.0 | yes — wake word over music, barge-in during TTS, STT, encrypted API |
| Extra cost | - | more flash and PSRAM, a long first build (esp-sr + esp-gmf are fetched), `esphome 2026.6.5+` |

### Stock: how the shared I2S bus is handled

The board wires the **ES8311 (DAC) and the ES7210 (ADC) to the same BCLK/LRCLK
pins**, and only one device can drive those clocks. ESPHome also cannot run a
single I2S bus full-duplex: a microphone and a speaker on one bus each try to
init the port, and the second fails with "Parent bus is busy".

The layout that works, all on **stock ESPHome components**:

- **Two I2S buses** (two ports) over the shared pins. The **mic bus is the I2S
  master**: it is always capturing for the wake word, so it drives BCLK/LRCLK/MCLK
  continuously. The **speaker bus is a slave** that reads the mic's clock, so it
  never needs a port of its own to master.
- The ES8311 and ES7210 are stock and slave to the mic's clock.
- The mic is pinned to **16-bit** (the i2s_audio default is 32-bit); since the
  mic is master it sets the frame's slot width, and a 32-bit frame against the
  16-bit DAC comes out as noise.

This gives simultaneous capture + playback with no custom component. The
annotated config is `base/audio-stock.yaml`.

### AFE: how to opt in, and what changes

```
esphome run waveshare-va-afe.yaml
```

Start from `waveshare-va-afe.yaml` rather than just swapping the package file in
`waveshare-va.yaml` - the AFE path needs several substitutions set, and they are
documented inline in that file.

`esp_audio_stack` owns one I2S port full-duplex from a single pinned task, so the
two-bus master/slave split is unnecessary there. It drives both codecs through
`esp_codec_dev`, captures the two mics and the ES8311's playback reference as
slots of the same TDM frame, converts that down to 16 kHz, and hands
`esp_afe` a sample-aligned reference. micro_wake_word and Assist then consume the
post-AEC stream.

Trade-offs and things that genuinely change:

- **The TDM slot map is contested.** Four sources give three answers; the
  defaults follow the one config asserted as measured on this board. The path
  ships four `TDM slot N level` diagnostic sensors to settle it, and every slot
  is a substitution you can flip. Full detail in
  [docs/HARDWARE.md](docs/HARDWARE.md#-tdm-slot-map-four-sources-three-answers).
- **`Mic gain (ES7210)` becomes `Mic gain (digital)`.** Stock exposes the
  ES7210's analog PGA (0 to 37.5 dB). On the AFE path the analog gain is
  compile-time - it also feeds the echo reference, so it is not safe as a live
  control - and the runtime entity is digital trim *after* the AFE
  (-20 to +30 dB).
- **A new `Master Volume`**, plus `Echo Cancellation`, `Voice Activity Detector`
  and `Voice Detected`. The media player's volume clamps are opened to 0-100%
  and loudness is shaped by the codec curve instead, so nothing is scaled twice.
- **Logging defaults to INFO**, because per-frame logging on the audio core is
  itself enough to glitch the audio.
- **No forked components.** The upstream ESPHome `speaker`, `voice_assistant` and
  `ota` are used as-is.

This path is **confirmed working on hardware**: the wake word lands over music
and during a TTS reply, STT quality holds up, and the encrypted API is stable.
The TDM slot map was verified with the on-device slot-level sensors.

[docs/AFE-BRINGUP.md](docs/AFE-BRINGUP.md) is still the place to start on a new
board - it walks the slot map first, then the tests that actually measure the
feature, and ends with a table of every substitution to flip for each symptom.

## Repository layout

```
waveshare-va.yaml          # YOUR config: copy + edit this (pulls the rest from GitHub)
waveshare-va-afe.yaml      # same, but on the opt-in AFE audio path
secrets.example.yaml       # copy to secrets.yaml
base/
  core.yaml                # the always-on core, minus audio hardware
  audio-stock.yaml         # audio path A (default): stock i2s_audio, no AEC
  audio-afe.yaml           # audio path B (opt-in): esp_audio_stack + esp_afe
docs/
  HARDWARE.md              # pinout, I2C map, gotchas
  AFE-BRINGUP.md           # hardware checklist + what to flip, for the AFE path
scripts/
  validate.py              # offline YAML check (syntax, substitutions, duplicate ids)
  esplog.py                # stream device logs over the native API
skill/
  waveshare-esp32-s3-audio/  # Claude Code skill: pinout + hard-won gotchas
```

## Configuration

Everything worth changing day to day is a Home Assistant entity, not a config
edit: mic gain, LED brightness, the ring animation per assistant phase
(Listening / Thinking / Replying effect), wake-word sensitivity, wake sound,
boot sound, microphone mute.

What lives in `waveshare-va.yaml`:

| Substitution | Default | What it does |
|---|---|---|
| `name` / `friendly_name` | `waveshare-va` / `Waveshare Voice` | Device name. Changing `name` re-creates every entity in HA. |
| `posix_timezone` | `CET-1CEST,...` | Clock zone in POSIX form (the device has no IANA database). DST automatic. |
| `volume_min` / `volume_max` | `0.2` / `0.6` | Media player clamps, because the onboard amp distorts near the top. |
| `hidden_ssid` | `false` | `true` enables `fast_connect` for a hidden SSID. |
| `boot_sound_file` | repo `startup.mp3` | The connect-to-HA chime. Any URL or local MP3/FLAC/WAV. |

Pins and the audio format are substitutions too (in `base/core.yaml`), but you
should not need them unless you are porting to another board.

## Claude Code skill

This repo ships a [Claude Code](https://claude.com/claude-code) skill at
[`skill/waveshare-esp32-s3-audio/`](skill/waveshare-esp32-s3-audio/SKILL.md):
the pinout, the shared-I2S constraint, and the gotchas that cost real debugging
time. Install it user-wide so any session picks it up:

```bash
cp -r skill/waveshare-esp32-s3-audio ~/.claude/skills/
```

## Credits

- **[jensenbox](https://github.com/jensenbox/waveshare-esp32-s3-audio)**: the
  ESP-master I2S layout for this board that the audio setup is based on.
- **[n-IA-hane/esphome-audio-stack](https://github.com/n-IA-hane/esphome-audio-stack)**:
  the `esp_audio_stack` / `esp_afe` components the AFE path is built on, and the
  [esphome-intercom](https://github.com/n-IA-hane/esphome-intercom) config for
  this board that its TDM slot map and task layout come from.
- **ESPHome**: everything the firmware is built out of.
- **[Home Assistant Voice PE](https://github.com/esphome/home-assistant-voice-pe)**:
  the sounds, and the phase/ducking model the LED state machine follows.
