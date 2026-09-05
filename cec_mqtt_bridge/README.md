![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg

<h2 align="left">Home Assistant App: HDMI-CEC MQTT Bridge</h2>

<div align="right">
  <a href="https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app#donate"><img src="https://img.shields.io/static/v1?label=DONATE&message=USDT%20&labelColor=555&color=26A17B&style=for-the-badge" alt="DONATE USDT"></a> &thinsp; <a href="https://donate.stream/donate_6a8404d5ea133"><img src="https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white" alt="DONAT.stream"></a>
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


## SEE DOCUMENTATION TAB FOR MORE DETAILS



### Support the project
[![DONAT.stream](https://img.shields.io/badge/DONATE.steam-fc0?style=for-the-badge&logo=heart&logoColor=white)](https://donate.stream/donate_6a8404d5ea133)  

![USDT](https://img.shields.io/badge/USDT-26A17B?style=for-the-badge&logo=tether&logoColor=white)  
TRC-20 — TQrwpY2LWF96YBbBSZZawRqQ6j9K4PzPQo   
ETHEREUM — 0x963798c6219b4df6442192be1c89a8b852cc4830  
POLYGON — 0x8051a1cf7a3b41221d723f7eae77d59d14fb275b  
BEP-20 — 0x2a1581bcbd2dc64b9d0f494c636d1d5dacb898e6  
TON — EQBetln-nWakoK3LaTOn8l8oqnhNZgbVMHq_neSPPA6tS6nS  
