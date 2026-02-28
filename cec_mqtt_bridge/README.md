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
MQTT broker [Mosquitto](https://github.com/home-assistant/addons/blob/master/mosquitto/DOCS.md)

---
SEE DOCUMENTATION TAB FOR MORE DETAILS.
