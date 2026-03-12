[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Home Assistant add-on: HDMI-CEC MQTT Bridge
========================================

Connect your AV devices to your home automation system.

## Features
 - Home Assistant entities for control power, volume and mute (complete set for a media player entity)
 - Power, volume (specific/up/down), and mute/unmute control and state feedback via MQTT
 - Receive all raw HDMI-CEC codes from the CEC bus and use them as triggers in automations.
 - Send any custom raw HDMI-CEC commands directly to the CEC bus via MQTT

## Supported hardware
### Raspberry Pi 3 / 4 / 5
- **RPi 4/5 limitation:** connection only via HDMI0 port (closest to the power connector).

### x86_64 / ODROID
- Not all devices have built-in HDMI-CEC support.
- If your system does not support HDMI-CEC, you can use an external USB-CEC adapter (such as the [Pulse-Eight](https://www.pulse-eight.com/p/104/usb-hdmi-cec-adapter)).

## Dependencies
MQTT broker [Mosquitto](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md)

## Configuring the CEC port
If you do not specify a port in the settings, the application will launch the libCEC adapter auto-detection feature (DetectAdapters) and open the first cec-adapter it finds.

> If you have more than one CEC adapter connected, you may need to set the port explicitly to avoid picking the wrong one.

## ⚠️ Volume correction
Different AVR brands use different volume scales. Set the maximum value of your AVR’s native volume scale in the add-on settings. This allows the add-on to correctly convert it to the normalized 0–100% volume scale.

MQTT topics `/cec/audio/volume` and `/cec/audio/volume/set` always use the normalized 0–100% range.

> If there is no AVR or any other device of type “Audio” on your CEC bus (device `laddr` 5), volume control is very likely not to work.

## Home Assistant entities
- Power switches for supported TV/AVR devices (`laddr` 0 and 5)
- Volume numbers (0-100%, native, normalized)
- Mute switch
- CEC status sensor

Optional sensors:
- Last received CEC message
- Last sent CEC message

## Home Assistant `media_player` example 
The app provides the full set of entities needed to build a Home Assistant universal media player for an AVR or TV.
```
media_player:
  - platform: universal
    name: AVR
    unique_id: hdmi_cec_avr

    commands:
      turn_on:
        action: switch.turn_on
        target:
          entity_id: switch.hdmi_cec_mqtt_bridge_sony_str_dh750  # replace with your power switch entity

      turn_off:
        action: switch.turn_off
        target:
          entity_id: switch.hdmi_cec_mqtt_bridge_sony_str_dh750  # replace with your power switch entity

      volume_up:
        action: mqtt.publish
        data:
          topic: cec-mqtt/cec/audio/volume/set
          payload: "up"

      volume_down:
        action: mqtt.publish
        data:
          topic: cec-mqtt/cec/audio/volume/set
          payload: "down"

      volume_mute:
        action: switch.toggle
        target:
          entity_id: switch.hdmi_cec_mqtt_bridge_mute_cec_mqtt  # replace with your mute switch entity

      volume_set:
        action: number.set_value
        target:
          entity_id: number.hdmi_cec_mqtt_bridge_volume_level_0_1_cec_mqtt  # replace with your normalized volume entity
        data:
          value: "{{ volume_level }}"

    # replace with your entitys
    attributes:
      state: switch.hdmi_cec_mqtt_bridge_sony_str_dh750  
      is_volume_muted: switch.hdmi_cec_mqtt_bridge_mute_cec_mqtt
      volume_level: number.hdmi_cec_mqtt_bridge_volume_level_0_1_cec_mqtt
```


## MQTT action examples
Volume `up` or `down`:
```
action: mqtt.publish
data:
  topic: cec-mqtt/cec/audio/volume/set
  payload: "up"
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


## MQTT Topics

### The bridge subscribes to the following topics:

| topic                               | body                                    | remark                                                                    |
|:------------------------------------|-----------------------------------------|---------------------------------------------------------------------------|
| `prefix`/cec/device/`laddr`/power/set | `on` / `off`                  | Turn on/off device with with logical address `laddr` (0-14).  |
| `prefix`/cec/audio/volume/set     | `integer (0-100)` / `up` / `down` | Sets the volume level of the audio system to a specific level or up/down. |
| `prefix`/cec/audio/mute/set       | `on` / `off`                      | Mute/Unmute the the audio system.                                         |
| `prefix`/cec/tx | `raw CEC command string(s)`                         | Send the specified raw CEC command string(s) to the CEC bus. You can specify multiple commands by separating them with a comma. Example: `cec/tx 15:44:41,15:45`. |

### The bridge publishes to the following topics:

| topic                                | body                              | remark                                                                         |
|:-------------------------------------|-----------------------------------|--------------------------------------------------------------------------------|
| `prefix`/cec/status                  | `online` / `offline`              | Report HDMI-CEC bus connection status.           |
| `prefix`/cec/device/`laddr`/type     | `string`                          | Report type of device with logical address `laddr` (0-14).      |
| `prefix`/cec/device/`laddr`/address  | `hex string (e.g. 0000, 1000, 2100)`     | Report physical address of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/active   | `True` / `False`                  | Report active source status of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/vendor   | `string`                          | Report vendor of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/osd      | `string`                          | Report OSD of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/cecver   | `string`                          | Report CEC version of device with logical address `laddr` (0-14).  |
| `prefix`/cec/device/`laddr`/power    | `on` / `off` / `unknown`          | Report power status of device with logical address `laddr` (0-14).      |
| `prefix`/cec/audio/volume            | `integer (0-100)` / `unknown`     | Report volume level of the audio system.         |
| `prefix`/cec/audio/volume_normalized | `float (0.00-1.00)` / `unknown`   | Report normalized audio volume in the 0.00-1.00 range. Intended for media-player style entities. |
| `prefix`/cec/audio/volume_native     | `integer (0-volume_correction)` / `unknown`   | Report audio volume in the AVR native scale after applying `volume_correction`. Useful when you need the device-specific absolute volume range instead of normalized or percent-based volume. |
| `prefix`/cec/audio/mute              | `on` / `off`                      | Report mute status of the audio system.          |
| `prefix`/cec/rx                      | `raw CEC command string`          | Notify that a raw CEC command string was received.              |

