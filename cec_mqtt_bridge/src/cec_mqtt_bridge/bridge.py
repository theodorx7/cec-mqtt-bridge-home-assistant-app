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
HA_ORIGIN_NAME = "cec-mqtt-bridge"
HA_SUPPORT_URL = "https://github.com/theodorx7/cec-mqtt-bridge-home-assistant-app"
HA_DISCOVERY_PREFIX_DEFAULT = "homeassistant"

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
        self.ha_rx_id = f"cec_last_received_{instance}"
        self.ha_tx_id = f"cec_last_sent_{instance}"
        self.ha_instance_label = instance
        self.ha_rx_discovery_topic = f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_rx_id}/config"
        self.ha_tx_discovery_topic = f"{HA_DISCOVERY_PREFIX_DEFAULT}/sensor/{self.ha_tx_id}/config"

        def mqtt_on_message(client: mqtt.Client, userdata, message):
            """Run mqtt callback in a seperate thread."""
            thread = threading.Thread(
                target=self.mqtt_on_message,
                args=(client, userdata, message),
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
        if self.config.get("mqtt_tls", False):
            self.mqtt_client.tls_set()
        
        self.mqtt_client.will_set(self.mqtt_prefix + '/bridge/status', 'offline', qos=1, retain=True)

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

        self.mqtt_client.loop_start()

        # Setup HDMI-CEC
        LOGGER.info("Initialising CEC...")
        self.cec_class = hdmicec.HdmiCec(
            port=self.config.get('cec_port') or "",
            name=self.config['cec_name'],
            devices=[int(x.strip()) for x in self.config['cec_devices'].split(',') if x.strip()],
            mqtt_send=self.mqtt_publish,
            volume_correction=self.config.get("volume_correction"),
        )
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
            (self.mqtt_prefix + '/cec/device/+/power/set', 0),
            (self.mqtt_prefix + '/cec/audio/volume/set', 0),
            (self.mqtt_prefix + '/cec/audio/mute/set', 0),
            (self.mqtt_prefix + '/cec/tx', 0),
            (self.mqtt_prefix + '/cec/refresh', 0),
            (self.mqtt_prefix + '/cec/scan', 0),
        ])

        # Publish birth message
        self.mqtt_publish('bridge/status', 'online', qos=1, retain=True)
        # HA MQTT Device Discovery toggle
        if self.ha_discovery_enabled:
            self._ha_publish_device_discovery()

    def mqtt_publish(self, topic, message=None, qos=0, retain=True):
        """Publish a MQTT message prefixed with bridge prefix

        Args:
            topic (str): The topic that the message should be published on
            message (_type_, optional): _description_. Defaults to None.
            qos (int, optional): _description_. Defaults to 0.
            retain (bool, optional): _description_. Defaults to True.
        """
        LOGGER.debug('Send to topic %s: %s', topic, message)
        self.mqtt_client.publish(self.mqtt_prefix + '/' + topic, message, qos=qos, retain=retain)

    def _ha_publish_device_discovery(self) -> None:
        device_ctx = {
            "identifiers": [self.ha_device_id],
            "name": "HDMI-CEC MQTT Bridge",
        }
        origin_ctx = {
            "name": HA_ORIGIN_NAME,
            "support_url": HA_SUPPORT_URL,
        }

        rx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Last Received CEC ({self.ha_instance_label})",
            "unique_id": self.ha_rx_id,
            "state_topic": f"{self.mqtt_prefix}/cec/rx",
        }
        tx_payload = {
            "device": device_ctx,
            "origin": origin_ctx,
            "name": f"Last Sent CEC ({self.ha_instance_label})",
            "unique_id": self.ha_tx_id,
            "state_topic": f"{self.mqtt_prefix}/cec/tx",
        }
    
        self.mqtt_client.publish(self.ha_rx_discovery_topic, json.dumps(rx_payload), qos=1, retain=True)
        self.mqtt_client.publish(self.ha_tx_discovery_topic, json.dumps(tx_payload), qos=1, retain=True)

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
        topic = message.topic.replace(self.mqtt_prefix, '').split('/')[1:]
        action = message.payload.decode()
        LOGGER.debug("Command received: %s (%s)", topic, message.payload)
        
        if topic[0] == 'cec':

            if topic[1] == 'device':
                device = int(topic[2])
                if topic[3] == 'power':
                    if action == 'on':
                        self.cec_class.power_on(device)
                    elif action == 'standby':
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
        self.mqtt_publish('bridge/status', 'offline', qos=1, retain=True)
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
            if bridge.cec_class and refresh_delay:
                bridge.cec_class.refresh()
                stop_event.wait(refresh_delay)
            else:
                stop_event.wait(3600)
    finally:
        bridge.cleanup()


if __name__ == '__main__':
    main()
