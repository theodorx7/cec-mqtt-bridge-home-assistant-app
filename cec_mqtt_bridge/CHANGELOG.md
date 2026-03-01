## 1.0.0
This project is based on core parts of [`ballle98/cec-mqtt-bridge`](https://github.com/ballle98/cec-mqtt-bridge), which also includes IR/LIRC functionality.
This implementation is **CEC-only**: IR/LIRC support (code paths, config sections, MQTT topics) has been removed.
Configuration is now read from Home Assistant add-on options (`/data/options.json`).  Legacy INI/CLI/default config handling has been removed; option keys are now flat (`mqtt_*`, `cec_*`).

## ✅ Fix: reliable `volume_set`

- Fixed a hang/loop scenario in `volume_set()` where the initial audio status request (`tx_command('71')`) could time out without unblocking:
  `CEC_OPCODE_REPORT_AUDIO_STATUS` now signals `volume_update`, so `volume_set()` reliably proceeds after the status query.
- Retry logic is now bounded: timeout counts as an attempt, max attempts reduced to **5**, and logs show progress.
- Improved AVR compatibility: `volume_set()` now uses **per-step** `VolumeUp()` / `VolumeDown()` clicks with a small delay instead of the previous hold-style “fast” mode (more reliable on devices that rate-limit/drop rapid press/hold sequences).

## 🔌 New CEC adapter open logic

- Refactored adapter opening into a single flow:
  - If a port is specified — open it directly.
  - Otherwise autodetect via libCEC `DetectAdapters()` and try candidates.
- Logs now include the selected port and whether it was opened via explicit config or autodetect; failures produce a single actionable error.
- Removed OS-specific `/dev/cec0` / `RPI` fallback logic.

## 🧵 MQTT

- `on_message` is handled in a **daemon thread**, avoiding blocked process shutdown.
- MQTT `client_id` is passed explicitly when creating the paho-mqtt client.
- Minor import/type-hint cleanups.

## 🧹 Cleanup

- Simplified libCEC callbacks and removed redundant `GetDevicePhysicalAddress()` call in `scan()`.
- Minor formatting.


**Full Changelog**: https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app/commits/1.0.0
