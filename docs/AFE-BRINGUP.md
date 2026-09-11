# AFE path: hardware bring-up checklist

The AFE audio path (`base/audio-afe.yaml`, flashed via `waveshare-va-afe.yaml`)
is **confirmed working on hardware**: wake word over music, barge-in during a
TTS reply, STT quality, the encrypted API and the TDM slot map have all been
verified on a real board. The stock path (`waveshare-va.yaml`) remains the
default and the fallback.

Work through this checklist anyway on a new board or a new board revision - the
slot map in particular is a per-board fact, and the shipped defaults are what
one board measured, not a guarantee.

Two results worth knowing before you start:

- **`afe_mode: high_perf` does not work on this board**, retested after the
  Wi-Fi and lwIP memory fixes. `low_cost` is the default for that reason.
- **API encryption is fine** once the memory settings are right. Bring up with
  it off only to reduce variables, then turn it back on.

Stream logs with `scripts/esplog.py` rather than the dashboard; the interesting
events are boot-time and easy to miss.

## Before anything: confirm you are on the AFE build

Both thin configs use the same `name:`, so they produce the same Home Assistant
device, the same entity ids and the same ESPHome build directory. Nothing in HA
tells you which one is flashed, and flashing the wrong file is easy.

The tell is the mic-gain entity: **`Mic gain (ES7210)` means you are on the
stock path**; the AFE path shows `Mic gain (digital)` plus `Echo Cancellation`,
`Master Volume` and the four `TDM slot N level` sensors. If both files are in
your ESPHome dashboard they will both claim the same device and OTA to the same
IP, so consider removing the stock entry while testing.

## Internal RAM: the real constraint on this path

Flash is a non-issue on a 16 MB board. **Internal RAM is what breaks things**,
and it breaks them in a very misleading order - each symptom is just the next
most expensive thing failing to allocate:

| Symptom | Cause |
|---|---|
| Encrypted API handshake never completes; `handshake timeout; disconnecting` after 60 s, forever | Noise handshake cannot allocate. Note a *wrong key* fails in milliseconds with a decrypt error, so a 60 s timeout is **not** a key problem. |
| API authenticates, then HA disconnects after exactly 60 s and retries forever; the ring never leaves the boot animation | Entity enumeration cannot complete in HA's 60 s budget. `init_in_progress` only clears on `voice_assistant.on_client_connected`, so the ring stays on the boot animation and the boot chime never plays. |
| `HTTP_CLIENT: Failed to allocate memory for host header` / `http_utils_assign_string: Memory exhausted` on a TTS reply | The media/TTS HTTP fetch cannot allocate. |

All three are the same problem. Two things matter:

1. **The TDM DMA rings take ~64 KB of internal heap** at I2S start. Watch the
   boot log: `Memory[before_i2s_prepare]` vs `Memory[after_i2s_enable]`. Under
   about 30 KB free with a ~20 KB largest block is where this starts hurting.
2. **`malloc()` can never reach PSRAM here.** ESPHome's `psram:` component sets
   `CONFIG_SPIRAM_USE_CAPS_ALLOC`, not `SPIRAM_USE_MALLOC`, so every small
   allocation in esp_http_client and friends competes for internal RAM only.
   PSRAM placement options help only the components that ask for PSRAM
   explicitly.

`base/audio-afe.yaml` already ships the mitigations: `afe_mode: low_cost`,
`network: enable_high_performance: false` (the speaker media_player otherwise
requests 65 KB lwIP TCP windows), trimmed Wi-Fi buffer pools, the mWW task stack
in PSRAM, and PSRAM placement for the audio/AFE buffers. If you still hit these
errors, next levers in order: swap `afe_feed_task_core`/`afe_fetch_task_core`,
then drop `micro_wake_word` to a single model.

Bring up with **API encryption off** and add it back once playback works; it is
the single most expensive thing at connection time, and it fails silently
(ESPHome compiles out the noise handshake error logging below VERY_VERBOSE).

## 0. First: confirm the TDM slot map

Everything downstream depends on this, and four sources disagree about it (see
[HARDWARE.md](HARDWARE.md#-tdm-slot-map-four-sources-three-answers)). Do this
before judging any audio quality result.

1. Open the four `TDM slot N level` sensors in Home Assistant.
2. **Play music.** Exactly one slot should track the music. That is the playback
   reference. Expected: **slot 1**.
3. **Speak, with playback stopped.** Two slots should track your voice. Expected:
   **slot 0** (right mic) and **slot 2** (left mic).
4. **Cover one mic at a time** to confirm which physical capsule is which.
   Expected with the board speaker-down and the GPIO header up: slot 0 = right,
   slot 2 = left. (Left/right being swapped is harmless for BSS - just fix the
   comments.)
5. Slot 3 should stay near-silent.

If the observed map differs, set the substitutions in `waveshare-va-afe.yaml`
(`tdm_mic_slot_a`, `tdm_mic_slot_b`, `tdm_ref_slot`) and reflash. The candidate
maps worth trying, in order of plausibility, are listed under
[Substitutions to flip](#substitutions-to-flip).

Expected on a known-good board (confirmed in this repo):

| Slot | Idle | Speech, playback stopped | Playback |
|---|---|---|---|
| 0 | ~-73 | rises, tracks slot 2 | rises (mic hears speaker) |
| 1 | ~-85 | **stays at floor** | rises most |
| 2 | ~-74 | rises, tracks slot 0 | rises (mic hears speaker) |
| 3 | ~-89 | flat | flat |

> Use **speech with playback stopped** as the discriminator. During playback the
> microphones pick up the speaker acoustically, so every live slot rises and the
> test proves nothing. Also watch the *idle* floors: the reference slot reads
> lower than the mics, because an electrical DAC tap has no capsule self-noise.

- [ ] Reference slot identified: \_\_\_
- [ ] Mic slots identified: \_\_\_ and \_\_\_

## 1. Do not wait for the reference-silent warning

`esp_audio_stack`'s README documents a
`TDM AEC reference silent for 100 frames ...` warning. **It cannot fire.** The
code is behind `USE_ESP_AUDIO_STACK_TDM_REF_DIAGNOSTIC`, which nothing in the
component defines and which has no YAML option; it is absent from the build's
`defines.h`.

A wrong `tdm_ref_slot` is therefore **completely silent** - dead slot or live
microphone alike. Step 0 is the only thing that proves the map.

## 2. Wake word at 70% music volume

The headline feature. On the stock path this fails.

- [ ] Play music, set volume to 70%, say the wake word from ~2 m. Ring goes violet.
- [ ] Repeat 10x; note the hit rate: \_\_\_/10
- [ ] Compare against the stock firmware at the same volume and distance: \_\_\_/10

## 3. Barge-in during a TTS reply

- [ ] Ask something with a long answer, then say the wake word while it is
      speaking. The announcement should stop and a new session start.
- [ ] Confirm the ring follows (replying → waiting-for-command).

## 4. STT accuracy vs the stock path

Say the same 10 commands on each firmware, in a quiet room, from ~2 m.

- [ ] Stock: \_\_\_/10 transcribed correctly
- [ ] AFE: \_\_\_/10
- [ ] Repeat with the TV or a fan on. Stock: \_\_\_/10  AFE: \_\_\_/10

A *drop* on the AFE path in the quiet case usually means the mic slots are
wrong (BSS fed a reference or a dead slot as if it were a mic), not that the AFE
is bad. Go back to step 0.

## 5. Mute produces true silence

- [ ] Turn on `Microphone Mute`. The ring flashes red.
- [ ] With music playing, say the wake word repeatedly for 30 s: **nothing** may
      trigger.
- [ ] Unmute; the wake word works again without a reboot or audio restart.

## 6. Boot chime and amp behaviour

The amp handling genuinely differs from the stock path: `esp_audio_stack` tears
the speaker path down when idle, so the amp is powered off 30 s after playback
rather than left on forever.

- [ ] Cold boot: the ring lights, and there is **no hiss** before the chime.
- [ ] The boot chime plays once on HA connect, and is not clipped at the start
      (`boot_chime_delay` is 0 s here; raise it if the first ~100 ms is missing).
- [ ] No loud pop at the start or end of the chime.
- [ ] Wait 30 s after playback: the amp switches off. Listen for a click - a
      quiet one is normal, a loud pop is not.
- [ ] Play two sounds 5 s apart: the amp must **not** cycle between them.
- [ ] Reconnect HA (restart the HA API): the chime does **not** replay.

If the powerdown click is objectionable, raise `amp_idle_delay`; if idle hiss
returns, lower it.

## 7. Volume range

Volume works differently here: the media player is unclamped (0-100%) and
loudness is shaped by the codec curve via `Master Volume` and
`master_volume_min_db: -30.0`.

- [ ] `Master Volume` at 0% is silent.
- [ ] 70% is comfortably loud for a room.
- [ ] The top of the range does not audibly distort. If it does, clamp
      `volume_max` back toward the stock `0.8`.
- [ ] The three onboard buttons still change volume, and the ring flashes green.
- [ ] Nothing sounds like it is being scaled twice (a dead zone at the bottom,
      or everything quiet until ~80%). If so, one of the two clamps is still on.

## 8. Heap and PSRAM headroom under load

The real risk: `bad_alloc` during an Assist reply while media is playing.

- [ ] Start music from Music Assistant, then run a full Assist query over the top.
- [ ] Watch the log for `bad_alloc`, `Failed to allocate`, task watchdog resets,
      or `E (…) AFE` errors.
- [ ] Note free internal heap and largest free block at idle and under load.
- [ ] Leave music + periodic Assist running for 30 min; confirm free heap is flat
      rather than trending down.
- [ ] Confirm no reboot loop after 24 h.

If internal heap is the constraint, the PSRAM placement flags in
`base/audio-afe.yaml` are already on; the next lever is `esp_afe` `mode:
low_cost` instead of `high_perf`.

## 9. Regressions in the shared core

These are shared with the stock path and should be untouched, but the mic id and
boot ordering changed underneath them:

- [ ] LED ring state machine: boot, no-HA, listening, thinking, replying, error.
- [ ] `Diag: disable microphone` still silences and re-enables the mic.
- [ ] Wake-word sensitivity select still applies.
- [ ] Voice timers: set, count down on the ring, ring, and stop on a wake word.
- [ ] Entity names/ids in HA are unchanged from the stock path, apart from the
      documented additions (`Master Volume`, `Echo Cancellation`, `Voice Activity
      Detector`, `Voice Detected`, four `TDM slot N level`) and the mic-gain
      rename.

## A note on noise suppression

`base/audio-afe.yaml` sets `ns_enabled: true`, but on a **dual-mic** build
esp-sr's `afe_config_check()` prioritises BSS over noise suppression and may
clear `ns_init` outright. So do not expect a separately audible NS stage here -
Speech Enhancement/BSS is what is actually cleaning the signal, and NS is "on if
esp-sr keeps it". This is also why NS is not exposed as a runtime switch: it
could not be honoured reliably. If you specifically want WebRTC NS behaviour,
that is a single-mic (`mic_num: 1`) configuration, which gives up BSS.

## Build warnings you can ignore

The AFE path compiles clean, but adds three classes of warning the stock path
does not. All three are benign; they are listed here so a real one stands out.

- **`readdir / closedir / opendir is not implemented and will always fail`**,
  three linker warnings against `espressif__esp-sr`'s `model_path.c`. That is
  esp-sr's *SPIFFS model loading* path, which this firmware never calls - the AFE
  is configured from YAML, not from models on a filesystem. No SPIFFS partition
  is needed.
- **`'micro_wake_word_state_to_string' defined but not used`** and the same for
  `voice_assistant_state_to_string` (`-Wunused-function`). These are a direct
  consequence of `log_level: INFO`: the functions exist only to format DEBUG log
  lines. They disappear if you raise the log level.
- The **`rgb_order` deprecation** and the tflite `-Wshadow` / `-Wformat`
  warnings are pre-existing and appear on the stock path too.

## Reference build sizes

ESPHome 2026.8.2, esp-idf recommended, measured on this repo with
`esphome compile`. Useful as a baseline for spotting a build that has grown
unexpectedly.

| | Flash | Internal RAM (DIRAM) |
|---|---|---|
| Stock | 1,679,759 B · 20.7% of 8,126,464 B | 143,551 B · 42.0% of 341,760 B |
| AFE | 3,148,375 B · 38.7% | 177,243 B · 51.9% |
| Delta | **+1,468,616 B** (+18.0 pp) | **+33,692 B** (+9.9 pp) |

Flash is not a concern on a 16 MB board. Internal RAM at ~52% before runtime
allocation is the number to watch, which is what step 8 above is for - and why
the PSRAM placement flags are already enabled in `base/audio-afe.yaml`.

## Substitutions to flip

All of these live in the `substitutions:` block of `waveshare-va-afe.yaml`.

| Symptom | Substitution | Try |
|---|---|---|
| "TDM AEC reference silent" warning | `tdm_ref_slot` | `2` (schematic / Korvo-2 baseline), then `0` (Waveshare demo `"RMNM"`) |
| Echo not cancelled, no warning | `tdm_ref_slot` | It is pointed at a live mic. Use the slot sensors, don't guess. |
| Wake word/STT worse than stock in a *quiet* room | `tdm_mic_slot_a`, `tdm_mic_slot_b` | `[0, 1]` (schematic), `[1, 3]` (demo `"RMNM"`) |
| Wake word under playback weaker than hoped | `afe_type` | **`sr`** before anything else. `fd` bakes in NLP for two-way speech; `sr`'s linear AEC preserves the spectrum micro_wake_word was trained on. The default is `fd` only because that is what was qualified on this board, in a build that was also a SIP intercom. |
| Internal RAM too tight | `afe_mode` | `low_cost` instead of `high_perf` |
| Capture is garbage, not merely misrouted | `tdm_bits_per_sample`, `tdm_slot_bit_width` | `32` and `32` (the audio-stack README's generic TDM examples) |
| Echo worse at high volume; reference clipping | `es7210_gain_db` | Leave it, and instead set `codec.input.ref_channel` + `ref_gain_db` in `base/audio-afe.yaml` - lowering the shared gain also starves the mics |
| Mics too quiet overall | `es7210_gain_db` | Up from `24.0` toward `37.5`, watching for reference clipping |
| Assist input too quiet / too hot | `va_volume_multiplier` | `1.0` to `4.0` (default `2.0`) |
| Everything too quiet until near max | `master_volume_min_db` | `-20.0` (less range, more usable bottom) |
| Distortion near the top | `volume_max` | Back down to `0.8` |
| Amp clicks between sounds | `amp_idle_delay` | Longer, e.g. `60s` |
| Idle hiss returns | `amp_idle_delay` | Shorter, e.g. `10s` |
| Chime start clipped | `boot_chime_delay` | `500ms` |
| AFE task watchdog resets | `afe_feed_task_core` / `afe_fetch_task_core` | Must differ. Try swapping them (`1` / `0`) |
| Audio stutters under Wi-Fi load | `audio_task_core`, `audio_task_priority` | `0` / `19`, or priority up to `21` |
| Chasing a bug | `log_level` | `DEBUG` - but expect the logging itself to cause dropouts |

### Full fallback

If the hardware reference cannot be made to work at all, set
`use_tdm_reference: false` in `base/audio-afe.yaml`. The stack falls back to a
software reference derived from the playback stream: AEC quality drops, but the
path still works. If that also disappoints, the stock path is unchanged and
still the default.
