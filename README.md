[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Home Assistant App: HDMI-CEC MQTT Bridge
========================================

Connect yours AV-devices to your Home Automation system. You can control and monitor power status and volume

## Features
 - Power control and feedback
 - Volume control (specific/up/down) and feedback
 - Relay HDMI-CEC messages from HDMI to broker (RX)
 - Relay HDMI-CEC messages from broker to HDMI (TX)

### Note
This project is based on core parts of [`ballle98/cec-mqtt-bridge`](https://github.com/ballle98/cec-mqtt-bridge), which also includes IR/LIRC functionality.
This implementation does not include IR/LIRC; only HDMI-CEC ↔ MQTT is supported.


## Supported hardware
### Raspberry Pi 3 / 4 / 5
- **RPi 4/5 limitation:** connection only via HDMI0 port (closest to the power connector).

### x86_64 / ODROID
- Not all devices have built-in HDMI-CEC support. To determine if your system currently supports HDMI-CEC, use the official HA [CEC Scanner](https://github.com/home-assistant/addons/blob/master/cec_scan/DOCS.md) app.
- If your system does not support HDMI-CEC, you can use an external USB-CEC adapter (such as the [Pulse-Eight](https://www.pulse-eight.com/p/104/usb-hdmi-cec-adapter)).

## Dependencies
MQTT broker (for example [Mosquitto](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md))

## Install
### Click on the button
[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](
https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Ftheodorx7%2Fcec-mqtt-bridge-home-assistant-app
)
### Or perform the steps manually
1. Navigate in your Home Assistant frontend to <kbd>Settings</kbd> -> <kbd>Apps</kbd> -> <kbd>Apps Store (Bottom Right)</kbd>.
2. Click the 3-dots menu at upper right <kbd>⋮</kbd> > <kbd>Repositories</kbd> and add this repository's URL: [https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app](https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app)
3. Refresh the page and find the "HDMI-CEC MQTT Bridge" app.


## Configuring the CEC port
If you do not specify a port in the settings, the application will launch the libCEC adapter auto-detection feature (DetectAdapters) and open the first adapter it finds.

> If you have more than one CEC adapter connected, you may need to set the port explicitly to avoid picking the wrong one.

## MQTT Topics

### The bridge subscribes to the following topics:

| topic                       | body                                    | remark                                                                    |
|:----------------------------|-----------------------------------------|---------------------------------------------------------------------------|
| `prefix`/cec/device/`laddr`/power/set | `on` / `standby`              | Turn on/standby device with with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/active/set | `yes` / `no`                 | activate/deactivate device with with logical address `laddr` (0-14).  |
| `prefix`/cec/audio/volume/set     | `integer (0-100)` / `up` / `down` | Sets the volume level of the audio system to a specific level or up/down. |
| `prefix`/cec/audio/mute/set       | `on` / `off`                      | Mute/Unmute the the audio system.                                         |
| `prefix`/cec/tx             | `commands`                              | Send the specified `commands` to the CEC bus. You can specify multiple commands by separating them with a space. Example: `cec/tx 15:44:41,15:45`. |

### The bridge publishes to the following topics:

| topic                          | body                                    | remark                                           |
|:-------------------------------|-----------------------------------------|--------------------------------------------------|
| `prefix`/bridge/status               | `online` / `offline`                    | Report availability status of the bridge.        |
| `prefix`/cec/device/`laddr`/type     | `on` / `off`                            | Report type of device with logical address `laddr` (0-14).      |
| `prefix`/cec/device/`laddr`/address  | `on` / `off`                            | Report physical address of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/active   | `yes` / `no`                            | Report active source status of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/vendor   | `string`                            | Report vendor of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/osd      | `string`                            | Report OSD of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/cecver   | `string`                            | Report CEC version of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/power    | `on` / `standby` / `toon` / `tostandby` / `unknown` | Report power status of device with logical address `laddr` (0-14).      |
| `prefix`/cec/device/`laddr`/language | `string`                            | Report langauge of device with logical address `laddr` (0-14).  |
| `prefix`/cec/audio/volume     | `integer (0-100)` /  `unknown = 127`                      | Report volume level of the audio system.         |
| `prefix`/cec/mute/status       | `on` / `off`                            | Report mute status of the audio system.          |
| `prefix`/cec/rx                | `command`                               | Notify that `command` was received.              |

`id` is the address (0-15) of the device on the CEC-bus.

## Examples of actions
Set a custom volume value (0 - 100):
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/audio/volume/set
  payload: "20"
```

Volume `up` or `down`:
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/audio/volume/set
  payload: "up"
```

Turn `on` or put the device into `standby` mode (AVR device address: `5`):
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/device/5/power/set
  payload: "on"
```
Request the AVR power status.
<br>
`15:8F` means initiator = 1, recipient = 5 (Recording Device 1 → Audio System 5), `8F` = cec-command:
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/tx
  payload: "15:8F"
```

Request the current volume level of a specific device (AVR address: `5`):
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/tx
  payload: "15:71"
```
