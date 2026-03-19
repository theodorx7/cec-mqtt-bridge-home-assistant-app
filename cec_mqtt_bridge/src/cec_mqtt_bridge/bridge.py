#!/usr/bin/env python3
"""Main HDMI CEC MQTT bridge module"""
import json
import logging
import signal
import threading
import time

import paho.mqtt.client as mqtt

from cec_mqtt_bridge import hdmicec

LOGGER = logging.getLogger('bridge')
HA_DISCOVERY_PREFIX_DEFAULT = "homeassistant"
HA_ORIGIN_NAME = "cec-mqtt-bridge"
HA_SUPPORT_URL = "https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app"

class Bridge:
    """Main bridge class"""

    def __init__(self, config: dict):
        self.config = config
        self.ha_optional_entities_enabled = self.config["ha_discovery"]
        self.ha_device_id = "cec_mqtt_bridge"
        self.mqtt_prefix = self.config["mqtt_prefix"]
        instance = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in self.mqtt_prefix)
        self.ha_instance_label = instance
        
        self.ha_optional_entity_ids = {
            "rx": f"cec_last_received_{instance}",
            "tx": f"cec_last_sent_{instance}",
        }
        self.ha_core_entity_ids = {
            "cec_status": f"cec_bus_status_{instance}",
            "volume": f"cec_volume_{instance}",
            "volume_normalized": f"cec_volume_normalized_{instance}",
            "volume_native": f"cec_volume_native_{instance}",
            "mute": f"cec_mute_{instance}",
        }
        self.ha_power_switch_devices = (0, 5)

        def mqtt_on_message(client: mqtt.Client, userdata, message):
            """Run mqtt callback in a separate thread."""
            thread = threading.Thread(target=self.mqtt_on_message, args=(client, userdata, message), daemon=True)
            thread.start()

        # Setup MQTT
        LOGGER.info("Initialising MQTT...")
        self.mqtt_client = mqtt.Client(client_id=self.config['mqtt_name'])
        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_message = mqtt_on_message
        user = self.config.get('mqtt_user')
        if user:
            self.mqtt_client.username_pw_set(
                user,
                password=self.config.get('mqtt_password') or ""
            )
        if self.config.get("mqtt_tls"):
            self.mqtt_client.tls_set()
        
        self.mqtt_client.will_set(f"{self.mqtt_prefix}/cec/status", "offline", qos=1, retain=True)

        tries = 30
        while tries > 0:
            tries -= 1
            try:
                self.mqtt_client.connect(self.config['mqtt_broker'],
                                         int(self.config['mqtt_port']), 60)
                break
            except ConnectionRefusedError:
                LOGGER.error("Connection was refused by the server")
            except OSError as err:
                LOGGER.error("OS error: %s", str(err))

            if tries > 0:
                LOGGER.debug("Retrying in 10 seconds... (%d tries left)", tries)
                time.sleep(10)
        else:
            LOGGER.error("Failed to connect to the MQTT broker after multiple attempts")
            raise ConnectionError('MQTT connect retries exhausted. Can\'t continue.')

        # Setup HDMI-CEC
        LOGGER.info("Initialising CEC...")
        self.cec_class = hdmicec.HdmiCec(
            port=self.config.get('cec_port') or "",
            name=self.config['cec_name'],
            devices=[int(x) for x in self.config["cec_devices"].replace(",", " ").split()],
            mqtt_send=self.mqtt_publish,
            volume_correction=self.config.get("volume_correction"))

        self.mqtt_client.loop_start()

    def mqtt_on_connect(self, client: mqtt.Client, _userdata, _flags, ret):
        """Handle MQTT connection establishment"""
        if ret == 0:
            LOGGER.info("Connected successfully")
        else:
            LOGGER.error("Connection failed with code %d", ret)
            return

        # Subscribe to CEC commands
        client.subscribe([
            (f"{self.mqtt_prefix}/cec/device/+/power/set", 0),
            (f"{self.mqtt_prefix}/cec/audio/volume/set", 0),
            (f"{self.mqtt_prefix}/cec/audio/mute/set", 0),
            (f"{self.mqtt_prefix}/cec/tx/set", 0),
            (f"{self.mqtt_prefix}/cec/refresh", 0),
            (f"{self.mqtt_prefix}/cec/scan", 0),
        ])

        self._ha_publish_core_device_discovery()

        if self.ha_optional_entities_enabled:
            self._ha_publish_optional_device_discovery()
        else:
            self._ha_clear_optional_device_discovery()
        
        threading.Thread(
            target=lambda: (self.scan(), self.cec_class.publish_status(force=True)), daemon=True).start()
        
    def mqtt_publish(self, topic, message=None, qos=0, retain=True):
        """Publish an MQTT message under the configured bridge prefix"""
        LOGGER.debug('Send to topic %s: %s', topic, message)
        return self.mqtt_client.publish(
            f"{self.mqtt_prefix}/{topic}",
            message,
            qos=qos,
            retain=retain,
        )

    def scan(self):
        """Scan HDMI-CEC devices and publish topics."""
        if self.cec_class.scanning:
            LOGGER.debug("Skipping scan: scan in progress")
            return

        self.cec_class.scanning = True
        try:
            if self.cec_class.refreshing:
                LOGGER.debug("Waiting for refresh to finish before scan")
            while self.cec_class.refreshing:
                time.sleep(0.1)

            LOGGER.debug("requesting CEC bus information ...")
            
            for device in self.cec_class.devices:
                physical_address = self.cec_class.cec_client.GetDevicePhysicalAddress(device)
                if physical_address == 0xFFFF:
                    continue

                vendor_id = self.cec_class.cec_client.GetDeviceVendorId(device)
                active = self.cec_class.cec_client.IsActiveSource(device)
                cec_version = self.cec_class.cec_client.GetDeviceCecVersion(device)
                power = self.cec_class.cec_client.GetDevicePowerStatus(device)
                osd_name = self.cec_class.cec_client.GetDeviceOSDName(device)

                vendor = self.cec_class.cec_client.VendorIdToString(vendor_id)
                power_str = self.cec_class.cec_client.PowerStatusToString(power)

                self.mqtt_publish(f'cec/device/{device}/type', self.cec_class.cec_client.LogicalAddressToString(device))
                self.mqtt_publish(f'cec/device/{device}/address', f'{physical_address:04x}')
                self.mqtt_publish(f'cec/device/{device}/active', str(active))
                self.mqtt_publish(f'cec/device/{device}/vendor', vendor)
                self.mqtt_publish(f'cec/device/{device}/osd', osd_name)
                self.mqtt_publish(f'cec/device/{device}/cecver', self.cec_class.cec_client.CecVersionToString(cec_version))
                power_state = hdmicec.HA_POWER_MAP.get(power_str, power_str)
                self.mqtt_publish(f'cec/device/{device}/power', power_state)

                vendor_clean = (vendor or "").strip()
                osd_clean = (osd_name or "").strip()

                if (
                    device in self.ha_power_switch_devices
                    and vendor_clean
                    and vendor_clean.lower() != "unknown"
                    and osd_clean
                    and osd_clean.lower() != "unknown"
                    and power_state in ("on", "off")
                ):
                    entity_id = f"cec_device_{device}_power_{self.ha_instance_label}"
                    payload = {
                        "device": {
                            "identifiers": [self.ha_device_id],
                            "name": "HDMI-CEC MQTT Bridge",
                        },
                        "origin": {
                            "name": HA_ORIGIN_NAME,
                            "support_url": HA_SUPPORT_URL,
                        },
                        "name": f"{vendor_clean} {osd_clean}",
                        "unique_id": entity_id,
                        "state_topic": f"{self.mqtt_prefix}/cec/device/{device}/power",
                        "command_topic": f"{self.mqtt_prefix}/cec/device/{device}/power/set",
                        "availability": [
                            {"topic": f"{self.mqtt_prefix}/cec/status"},
                        ],
                        "payload_available": "online",
                        "payload_not_available": "offline",
                        "payload_on": "on",
                        "payload_off": "off",
                        "state_on": "on",
                        "state_off": "off",
                        "icon": "mdi:power",
                    }

                    self.mqtt_client.publish(
                        f"{HA_DISCOVERY_PREFIX_DEFAULT}/switch/{entity_id}/config",
                        json.dumps(payload),
                        qos=1,
                        retain=True,
                    )

            self.cec_class._publish_audio_status(self.cec_class.cec_client.AudioStatus())
        finally:
            self.cec_class.scanning = False
    
    def _ha_publish_core_device_discovery(self) -> None:
        device_ctx = {
            "identifiers": [self.ha_device_id],
            "name": "HDMI-CEC MQTT Bridge",
        }
        origin_ctx = {
            "name": HA_ORIGIN_NAME,
            "support_url": HA_SUPPORT_URL,
        }
        availability = [
            {"topic": f"{self.mqtt_prefix}/cec/status"},
        ]
        cec_status_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"CEC Bus Status ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["cec_status"],
            "state_topic": f"{self.mqtt_prefix}/cec/status",
            "device_class": "enum",
            "options": ["online", "offline"],
            "icon": "mdi:hdmi-port",
        }
        volume_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Volume Level 0-100% ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["volume"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/volume",
            "command_topic": f"{self.mqtt_prefix}/cec/audio/volume/set",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_reset": "unknown",
            "unit_of_measurement": "%",
            "min": 0,
            "max": 100,
            "step": 1,
            "mode": "slider",
            "icon": "mdi:knob",
        }
        volume_native_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Volume Level 0-{int(self.config.get('volume_correction') or 100)} ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["volume_native"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/volume_native",
            "command_topic": f"{self.mqtt_prefix}/cec/audio/volume/set",
            "command_template": f"{{{{ (value | float * 100 / {int(self.config.get('volume_correction') or 100)}) | round(0) | int }}}}",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_reset": "unknown",
            "min": 0,
            "max": int(self.config.get('volume_correction') or 100),
            "step": 1,
            "mode": "slider",
            "icon": "mdi:volume-source",
        }
        volume_normalized_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Volume Level 0-1 ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["volume_normalized"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/volume_normalized",
            "command_topic": f"{self.mqtt_prefix}/cec/audio/volume/set",
            "command_template": "{{ (value | float * 100) | round(0) | int }}",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_reset": "unknown",
            "min": 0,
            "max": 1,
            "step": 0.01,
            "mode": "slider",
            "icon": "mdi:knob",
        }
        mute_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Mute ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["mute"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/mute",
            "command_topic": f"{self.mqtt_prefix}/cec/audio/mute/set",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_on": "on",
            "payload_off": "off",
            "state_on": "on",
            "state_off": "off",
            "icon": "mdi:volume-mute",
        }
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_core_entity_ids['cec_status']}/config",
            json.dumps(cec_status_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/number/{self.ha_core_entity_ids['volume_native']}/config",
            json.dumps(volume_native_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/number/{self.ha_core_entity_ids['volume']}/config",
            json.dumps(volume_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/number/{self.ha_core_entity_ids['volume_normalized']}/config",
            json.dumps(volume_normalized_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/switch/{self.ha_core_entity_ids['mute']}/config",
            json.dumps(mute_payload),
            qos=1,
            retain=True)

    def _ha_publish_optional_device_discovery(self) -> None:
        device_ctx = {
            "identifiers": [self.ha_device_id], "name": "HDMI-CEC MQTT Bridge"}
        origin_ctx = {
            "name": HA_ORIGIN_NAME,
            "support_url": HA_SUPPORT_URL}
        availability = [
            {"topic": f"{self.mqtt_prefix}/cec/status"}]
    
        rx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Received ({self.ha_instance_label})",
            "unique_id": self.ha_optional_entity_ids["rx"],
            "state_topic": f"{self.mqtt_prefix}/cec/rx",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:chevron-double-down",
        }
        tx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Sent ({self.ha_instance_label})",
            "unique_id": self.ha_optional_entity_ids["tx"],
            "state_topic": f"{self.mqtt_prefix}/cec/tx",
            "availability": availability,
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:chevron-double-up",
        }
    
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_optional_entity_ids['rx']}/config",
            json.dumps(rx_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_optional_entity_ids['tx']}/config",
            json.dumps(tx_payload),
            qos=1,
            retain=True)

    def _ha_clear_optional_device_discovery(self, *, wait: bool = False) -> None:
        infos = (
            self.mqtt_client.publish(
                f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_optional_entity_ids['rx']}/config", payload="", qos=1, retain=True),
            self.mqtt_client.publish(
                f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_optional_entity_ids['tx']}/config", payload="", qos=1, retain=True),
        )
        if wait:
            for info in infos:
                info.wait_for_publish(timeout=2)
    
    def mqtt_on_message(self, _client: mqtt.Client, _userdata, message):
        """Process a message received on a subscribed MQTT topic"""
        try:
            prefix = f"{self.mqtt_prefix}/"
            if not message.topic.startswith(prefix):
                LOGGER.warning("Unexpected MQTT topic: %s", message.topic)
                return
    
            topic = message.topic[len(prefix):].split('/')
            action = message.payload.decode()
            LOGGER.debug("Command received: %s (%s)", topic, message.payload)
    
            if not topic or topic[0] != 'cec':
                return
    
            if topic[1] == 'refresh':
                self.cec_class.refresh()
                return
    
            if topic[1] == 'scan':
                self.scan()
                return
    
            if topic[1:3] == ['tx', 'set']:
                for command in action.split(','):
                    command = command.strip()
                    if command:
                        self.cec_class.tx_command(command)
                return
    
            if topic[1:3] == ['audio', 'mute']:
                if action == 'on':
                    self.cec_class.volume_mute()
                    return
                if action == 'off':
                    self.cec_class.volume_unmute()
                    return
                raise ValueError(f"Unknown volume command: {topic} {action}")
    
            if topic[1:3] == ['audio', 'volume']:
                if action == 'up':
                    self.cec_class.volume_up()
                    return
                if action == 'down':
                    self.cec_class.volume_down()
                    return
                if action.isdigit() and int(action) <= 100:
                    self.cec_class.volume_set(int(action))
                    return
                raise ValueError(f"Unknown volume command: {topic} {action}")
    
            if len(topic) >= 4 and topic[1] == 'device' and topic[3] == 'power':
                device = int(topic[2])
                if action == 'on':
                    self.cec_class.power_on(device)
                    return
                if action == 'off':
                    self.cec_class.power_off(device)
                    return
                raise ValueError(f"Unknown power command: {topic} {action}")
    
        except Exception:
            LOGGER.exception(
                "Failed to process MQTT message: topic=%s payload=%s",
                message.topic,
                message.payload,
            )

    def cleanup(self):
        """Terminates the connection"""
        cec_info = self.cec_class.publish_status('offline', force=True)
        if cec_info is not None:
            cec_info.wait_for_publish(timeout=2)

        if not self.ha_optional_entities_enabled:
            self._ha_clear_optional_device_discovery(wait=True)
        
        self.mqtt_client.disconnect()
        self.mqtt_client.loop_stop()


def main():
    """main for cec_mqtt_bridge"""
    with open("/data/options.json") as f: config = json.load(f)
    log_level = logging.DEBUG if config.get("debug") else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(funcName)s: %(message)s",
    )

    bridge = Bridge(config)
    stop_event = threading.Event()
    
    def _signal_handler(signum, _frame):
        LOGGER.info("Received signal %s, stopping...", signum)
        stop_event.set()
    
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    def _heartbeat_loop():
        while not stop_event.wait(30):
            bridge.cec_class.heartbeat()
    
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    
    refresh_delay = int(bridge.config["cec_refresh"])
    if 0 < refresh_delay < 10:
        refresh_delay = 10

    LOGGER.debug("refresh delay %d", refresh_delay)

    try:
        while not stop_event.wait(refresh_delay or 3600):
            if refresh_delay:
                bridge.cec_class.refresh()
    finally:
        bridge.cleanup()

if __name__ == '__main__':
    main()
