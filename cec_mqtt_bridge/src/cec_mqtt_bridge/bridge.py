#!/usr/bin/env python3
"""Main HDMI CEC MQTT bridge module

Raises:
    ValueError: Invalid config value
    ConnectionError: Failed to connect to MQTT brocker
"""
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

def load_config_from_ha() -> dict:
    with open("/data/options.json", "r", encoding="utf-8") as f:
        return json.load(f)

class Bridge:
    """Main bridge class"""

    def __init__(self, config: dict):
        self.config = config
        self.ha_discovery_enabled = self.config["ha_discovery"]
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
            "volume_native": f"cec_volume_native_{instance}",
        }

        def mqtt_on_message(client: mqtt.Client, userdata, message):
            """Run mqtt callback in a separate thread."""
            def _runner():
                try:
                    self.mqtt_on_message(client, userdata, message)
                except Exception:
                    LOGGER.exception("Failed to process MQTT message: topic=%s payload=%s", message.topic, message.payload)
        
            thread = threading.Thread(
                target=_runner,
                daemon=True,
            )
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
        
        self.mqtt_client.will_set(f"{self.mqtt_prefix}/bridge/status", "offline", qos=1, retain=True)

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
            volume_correction=self.config.get("volume_correction"),
        )

        self.mqtt_client.loop_start()

    def mqtt_on_connect(self, client: mqtt.Client, _userdata, _flags, ret):
        """MQTT on connect callback

        Args:
            client (mqtt): _description_
            _userdata (_type_): _description_
            _flags (_type_): _description_
            ret (_type_): _description_
        """
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
            (f"{self.mqtt_prefix}/cec/tx", 0),
            (f"{self.mqtt_prefix}/cec/refresh", 0),
            (f"{self.mqtt_prefix}/cec/scan", 0),
        ])

        # Publish birth message
        self.mqtt_publish('bridge/status', 'online', qos=1, retain=True)
        
        self._ha_publish_core_device_discovery()
        
        if self.ha_discovery_enabled:
            self._ha_publish_optional_device_discovery()
        else:
            self._ha_clear_optional_device_discovery()
        
        self.cec_class.publish_status()

    def mqtt_publish(self, topic, message=None, qos=0, retain=True):
        """Publish a MQTT message prefixed with bridge prefix.

        Args:
            topic (str): The topic that the message should be published on
            message (_type_, optional): _description_. Defaults to None.
            qos (int, optional): _description_. Defaults to 0.
            retain (bool, optional): _description_. Defaults to True.
        """
        LOGGER.debug('Send to topic %s: %s', topic, message)
        return self.mqtt_client.publish(
            f"{self.mqtt_prefix}/{topic}",
            message,
            qos=qos,
            retain=retain,
        )

    def _ha_sensor_discovery_topic(self, entity_id: str) -> str:
        return f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{entity_id}/config"
    
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
            {"topic": f"{self.mqtt_prefix}/bridge/status"},
            {"topic": f"{self.mqtt_prefix}/cec/status"},
        ]
    
        cec_status_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"CEC Bus Status ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["cec_status"],
            "state_topic": f"{self.mqtt_prefix}/cec/status",
            "availability_topic": f"{self.mqtt_prefix}/bridge/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "device_class": "enum",
            "options": ["online", "offline"],
            "icon": "mdi:hdmi-port",
        }
    
        volume_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Volume Level (%) ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["volume"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/volume",
            "value_template": "{{ value_json.percent }}",
            "json_attributes_topic": f"{self.mqtt_prefix}/cec/audio/volume",
            "json_attributes_template": "{{ {'level': value_json.level} | tojson }}",
            "availability": availability,
            "availability_mode": "all",
            "payload_available": "online",
            "payload_not_available": "offline",
            "unit_of_measurement": "%",
            "icon": "mdi:volume-high",
        }
    
        volume_native_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Volume Level ({self.ha_instance_label})",
            "unique_id": self.ha_core_entity_ids["volume_native"],
            "state_topic": f"{self.mqtt_prefix}/cec/audio/volume_native",
            "availability": availability,
            "availability_mode": "all",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:volume-source",
        }
    
        self.mqtt_client.publish(
            self._ha_sensor_discovery_topic(self.ha_core_entity_ids["cec_status"]),
            json.dumps(cec_status_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            self._ha_sensor_discovery_topic(self.ha_core_entity_ids["volume"]),
            json.dumps(volume_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            self._ha_sensor_discovery_topic(self.ha_core_entity_ids["volume_native"]),
            json.dumps(volume_native_payload),
            qos=1,
            retain=True,
        )
    
    def _ha_publish_optional_device_discovery(self) -> None:
        device_ctx = {
            "identifiers": [self.ha_device_id],
            "name": "HDMI-CEC MQTT Bridge",
        }
        origin_ctx = {
            "name": HA_ORIGIN_NAME,
            "support_url": HA_SUPPORT_URL,
        }
        availability = [
            {"topic": f"{self.mqtt_prefix}/bridge/status"},
            {"topic": f"{self.mqtt_prefix}/cec/status"},
        ]
    
        rx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Last Received CEC ({self.ha_instance_label})",
            "unique_id": self.ha_optional_entity_ids["rx"],
            "state_topic": f"{self.mqtt_prefix}/cec/rx",
            "availability": availability,
            "availability_mode": "all",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:chevron-double-down",
        }
        tx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Last Sent CEC ({self.ha_instance_label})",
            "unique_id": self.ha_optional_entity_ids["tx"],
            "state_topic": f"{self.mqtt_prefix}/cec/tx",
            "availability": availability,
            "availability_mode": "all",
            "payload_available": "online",
            "payload_not_available": "offline",
            "icon": "mdi:chevron-double-up",
        }
    
        self.mqtt_client.publish(
            self._ha_sensor_discovery_topic(self.ha_optional_entity_ids["rx"]),
            json.dumps(rx_payload),
            qos=1,
            retain=True,
        )
        self.mqtt_client.publish(
            self._ha_sensor_discovery_topic(self.ha_optional_entity_ids["tx"]),
            json.dumps(tx_payload),
            qos=1,
            retain=True,
        )

    def _ha_clear_optional_device_discovery(self, *, wait: bool = False) -> None:
        infos = (
            self.mqtt_client.publish(self._ha_sensor_discovery_topic(self.ha_optional_entity_ids["rx"]), payload="", qos=1, retain=True),
            self.mqtt_client.publish(self._ha_sensor_discovery_topic(self.ha_optional_entity_ids["tx"]), payload="", qos=1, retain=True),
        )
        if wait:
            for info in infos:
                info.wait_for_publish(timeout=2)
    
    def mqtt_on_message(self, _client: mqtt.Client, _userdata, message):
        """Process message on subscibed MQTT topic

        Args:
            _client (mqtt): Not Used
            _userdata (_type_): Not Used
            message (_type_): topic and payload

        Raises:
            ValueError: _description_
            ValueError: _description_
            ValueError: _description_
        """
        # Decode topic and split off the prefix
        prefix = f"{self.mqtt_prefix}/"
        if not message.topic.startswith(prefix):
            LOGGER.warning("Unexpected MQTT topic: %s", message.topic)
            return
        
        topic = message.topic[len(prefix):].split('/')
        action = message.payload.decode()
        LOGGER.debug("Command received: %s (%s)", topic, message.payload)
        
        if topic[0] == 'cec':

            if topic[1] == 'device':
                device = int(topic[2])
                if topic[3] == 'power':
                    if action == 'on':
                        self.cec_class.power_on(device)
                    elif action == 'off':
                        self.cec_class.power_off(device)
                    else:
                        raise ValueError(f"Unknown power command: {topic} {action}")

            elif topic[1] == 'audio':
                if topic[2] == 'volume':
                    if action == 'up':
                        self.cec_class.volume_up()
                    elif action == 'down':
                        self.cec_class.volume_down()
                    elif action.isdigit() and int(action) <= 100:
                        self.cec_class.volume_set(int(action))
                    else:
                        raise ValueError(f"Unknown volume command: {topic} {action}")

                elif topic[2] == 'mute':
                    if action == 'on':
                        self.cec_class.volume_mute()
                    elif action == 'off':
                        self.cec_class.volume_unmute()
                    else:
                        raise ValueError(f"Unknown volume command: {topic} {action}")

            elif topic[1] == 'tx':
                for command in action.split(','):
                    if command.strip():
                        self.cec_class.tx_command(command.strip())

            elif topic[1] == 'refresh':
                self.cec_class.refresh()

            elif topic[1] == 'scan':
                self.cec_class.scan()

    def cleanup(self):
        """Terminates the connection"""
        bridge_info = self.mqtt_publish('bridge/status', 'offline', qos=1, retain=True)
        cec_info = self.mqtt_publish('cec/status', 'offline', qos=1, retain=True)
    
        bridge_info.wait_for_publish(timeout=2)
        cec_info.wait_for_publish(timeout=2)
    
        if not self.ha_discovery_enabled:
            self._ha_clear_optional_device_discovery(wait=True)
    
        self.mqtt_client.disconnect()
        self.mqtt_client.loop_stop()


def main():
    """main for cec_mqtt_bridge"""
    config = load_config_from_ha()
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
    
    refresh_delay = int(bridge.config["cec_refresh"])
    if 0 < refresh_delay < 10:
        refresh_delay = 10

    LOGGER.debug("refresh delay %d", refresh_delay)

    try:
        while not stop_event.is_set():
            # Refresh CEC state
            if refresh_delay:
                bridge.cec_class.refresh()
            stop_event.wait(refresh_delay or 3600)
    finally:
        bridge.cleanup()


if __name__ == '__main__':
    main()
