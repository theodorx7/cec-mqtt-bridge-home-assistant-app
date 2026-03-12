[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

Home Assistant add-on: HDMI-CEC MQTT Bridge
========================================

HDMI-CEC is a communication protocol that allows devices connected via HDMI to exchange control commands. Integrate your AV devices into Home Assistant automations.

## Features
 - Home Assistant entities for control power, volume and mute (complete set for a media player entity)
 - Receive all raw HDMI-CEC codes from the CEC bus and use them as triggers in automations.
 - Power, volume (specific/up/down), and mute/unmute control and state feedback via MQTT
 - Send any custom raw HDMI-CEC commands directly to the CEC bus via MQTT

## Supported hardware
### Raspberry Pi 3 / 4 / 5
- **RPi 4/5 limitation:** connection only via HDMI0 port (closest to the power connector).

### x86_64 / ODROID
- Not all devices have built-in HDMI-CEC support.
- If your system does not support HDMI-CEC, you can use an external USB-CEC adapter (such as the [Pulse-Eight](https://www.pulse-eight.com/p/104/usb-hdmi-cec-adapter)).

## Dependencies
MQTT broker [Mosquitto](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md)

---
SEE DOCUMENTATION TAB FOR MORE DETAILS.
