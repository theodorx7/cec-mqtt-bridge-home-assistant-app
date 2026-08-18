![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg

<h2 align="left">Home Assistant App: Navidrome Rating Sync</h2>

<div align="right">
  <a href="https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app/blob/main/.github/DONATE.md"><img src="https://img.shields.io/static/v1?label=USDT&message=SUPPORT&labelColor=26A17B&color=8b8b8b&style=for-the-badge&logo=tether&logoColor=white" alt="USDT TRC20"></a>&thinsp;<a href="https://donate.stream/donate_6a8404d5ea133"><img src="https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white" alt="DONAT.stream"></a>
</div>

HDMI-CEC lets your HDMI devices control each other.  
Easily integrate your TV and audio equipment into Home Assistant automations.

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
