## 2.0.0
### ⚠️ Breaking Changes
- Added a new MQTT command topic `cec/tx/set` for sending raw CEC commands. The `cec/tx` topic, which was previously used for this purpose, now publishes state only.
- The `Last Received CEC` and `Last Sent CEC` sensors were renamed to `Received` and `Sent`. The entity names and `unique_id`s were also changed.

### Added
- The `prefix/cec/tx` topic and the `Sent` sensor now expose all system commands, not only commands sent manually.
- Added a new, improved method for detecting HDMI-CEC Bus connection status (`online` / `offline`).

### Improved
- Improved devices power state update speed and debounce logic.
- Reduced redundant requests and unnecessary logical operations.

### Fixed
- Fixed an issue where some incoming CEC bus messages could be intermittently missing from the `prefix/cec/rx` topic and the `Received` sensor.


## 1.0.1
This project is based on `bridge.py` and `hdmicec.py` from [`michaelarnauts`](https://github.com/michaelarnauts/cec-mqtt-bridge) → [`ballle98`](https://github.com/ballle98/cec-mqtt-bridge). Since the goal was to create a solution tailored specifically to Home Assistant, the logic of the original `cec-mqtt-bridge` had to be significantly reworked.

### Added
- Full packaging of the project as a Home Assistant app.
- Publishing entities in Home Assistant:
  - sensor CEC Bus Status; numbers: Volume Level 0-100%, Volume Level 0-Native, Volume Level 0-1; switch Mute;
  - sensors: `Last Received CEC`, `Last Sent CEC` (can be disabled in the app settings);
  - power switches for TV (0) and AVR (5), if their name and current power state are available;
- Home Assistant entities use `cec/status` as the availability indicator;
- The `volume_correction` parameter has been exposed in the app settings and allows configuring the AVR’s native volume scale for correct operation of the `volume_set` command.
- Added two additional MQTT audio topics for volume: `cec/audio/volume_native` and `cec/audio/volume_normalized`, allowing the use of the native AVR scale and a normalized `0-1` value alongside the standard `0-100` level.
- Added the logic for suppressing the publication of outdated power/mute states.
- Added proper handling of an unknown volume level: if the AVR returns `0x7F`, the app publishes the state as `unknown` instead of an incorrect volume value.

### Changed
- The project has been migrated to a CEC-only model: IR/LIRC support, related MQTT topics, and configuration sections have been removed.
- The project’s configuration model has been redesigned for Home Assistant: instead of INI configuration, env overrides, and CLI flags, `/data/options.json` with flat `mqtt_*` and `cec_*` keys is now used.
- The CEC adapter opening logic has been reworked: when a port is specified, it is opened directly; otherwise, autodetection is performed via `libCEC DetectAdapters()`.
- State publishing has been reworked to support Home Assistant: the power state is normalized to `on/off`.
- The previous bridge status has been replaced with `cec/status`: it is now used as the availability indicator for HA entities and reflects not only whether the process is running, but also the connection state to the CEC bus.
- The `volume_set()` logic has been fully reworked for more accurate and stable AVR volume control: the app requests the current level, calculates the exact difference, sends the required number of stepwise `VolumeUp` / `VolumeDown` commands (without pauses), then verifies the result and performs an additional correction for reliability.
  - The **last request wins** principle has been implemented: a new volume request cancels the previous one so that outdated operations do not affect the final state.
- MQTT command handling has been moved to a separate daemon thread so that incoming messages do not interfere with the normal shutdown of the app.
- MQTT topics and Home Assistant discovery identifiers are now generated consistently based on the configured `mqtt_prefix`.

### Fixed
- Fixed the infinite `volume_set()` loop, which occurred because it was not receiving a response to the audio status request.
