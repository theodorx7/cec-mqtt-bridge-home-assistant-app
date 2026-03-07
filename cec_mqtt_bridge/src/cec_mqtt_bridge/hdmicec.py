#!/usr/bin/env python3
"""HDMI CEC interface to HDMI CEC MQTT bridge"""

import json
import logging
import math
import re
import threading
import time
from typing import Callable, Optional
import cec

SUPPRESS_S = 3.0

LOGGER = logging.getLogger(__name__)


class HdmiCec:
    """HDMI CEC interface class"""
    def __init__(
        self,
        port: str,
        name: str,
        devices: list[int],
        mqtt_send: Callable[..., None],
        volume_correction: int | None = None,
    ):
        self._mqtt_send = mqtt_send
        self.devices = devices
        self.volume_correction = 100 if volume_correction is None else volume_correction

        self.setting_volume = False
        self.refreshing = False
        self._suppress_until = {}
        self.volume_update = threading.Event()
        self._volume_token = 0
        self._volume_token_lock = threading.Lock()
        self._cec_connected = None

        self.cec_config = cec.libcec_configuration()
        self.cec_config.strDeviceName = name
        self.cec_config.bActivateSource = 0
        self.cec_config.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        self.cec_config.clientVersion = cec.LIBCEC_VERSION_CURRENT
        self.cec_config.SetLogCallback(self._on_log_callback)
        self.cec_config.SetKeyPressCallback(self._on_key_press_callback)
        self.cec_config.SetCommandCallback(self._on_command_callback)

        # Open connection
        self.cec_client = cec.ICECAdapter.Create(self.cec_config)  # type: cec.ICECAdapter
        selected_port, selected_source = self._open_cec_adapter(port)

        self.device_id = self.cec_client.GetLogicalAddresses().primary
        LOGGER.info(
            'Connected to HDMI-CEC with ID %d (port=%s, source=%s)',
            self.device_id,
            selected_port,
            selected_source,
        )
        self.scan()

    def _ha_power(self, p: str) -> str:
        return {"toon": "on", "standby": "off", "tostandby": "off"}.get(p, p)

    def _suppress(self, key: int | str):
        self._suppress_until[key] = time.monotonic() + SUPPRESS_S
    
    def _is_suppressed(self, key: int | str) -> bool:
        return time.monotonic() < self._suppress_until.get(key, 0)
    
    def _publish_power(self, device: int, power: str):
        if not self._is_suppressed(device):
            self._mqtt_send(f'cec/device/{device}/power', self._ha_power(power))
    
    def _publish_audio_status(self, audio_status: int, *, notify: bool = False):
        mute, volume_native = self.decode_volume(audio_status)
        volume_percent = self._native_to_percent(volume_native)
        volume_level = round(volume_percent / 100.0, 3)
    
        self._mqtt_send(
            'cec/audio/volume',
            json.dumps({
                "percent": volume_percent,
                "level": volume_level,
            }),
        )
        self._mqtt_send('cec/audio/volume_native', volume_native)
    
        if not self._is_suppressed("mute"):
            self._mqtt_send('cec/audio/mute', 'on' if mute else 'off')
        if notify:
            self.volume_update.set()
    
    def _set_cec_connected(self, connected: bool, force: bool = False):
        changed = self._cec_connected != connected
    
        if not force and not changed:
            return
    
        self._cec_connected = connected
        state = 'online' if connected else 'offline'
    
        if changed:
            LOGGER.info('CEC bus status changed: %s', state)
    
        self._mqtt_send('cec/status', state, qos=1, retain=True)

    def publish_status(self):
        if self._cec_connected is not None:
            self._set_cec_connected(self._cec_connected, force=True)

    def _open_cec_adapter(self, explicit_port: str) -> tuple[str, str]:
        """Open explicit libCEC port or first available autodetected adapter."""
        def try_open(port_name: str) -> bool:
            try:
                return bool(self.cec_client.Open(port_name))
            except Exception as err:
                LOGGER.debug('Open(%s) raised: %s', port_name, err)
                return False

        if explicit_port:
            if try_open(explicit_port):
                LOGGER.info('Opened HDMI-CEC device %s (source=explicit)', explicit_port)
                return explicit_port, 'explicit'
            LOGGER.error('CEC adapter explicit open failed (port=%s)', explicit_port)
            raise ConnectionError(f"Could not connect to CEC adapter on port '{explicit_port}'")

        try:
            adapters = self.cec_client.DetectAdapters() or []
        except Exception as err:
            LOGGER.error('Port autodetection mechanism failed (DetectAdapters): %s', err)
            raise ConnectionError('Could not connect to CEC adapter') from err

        last = None
        for adapter in adapters:
            candidate = getattr(adapter, 'strComName', None)
            if candidate:
                last = candidate
                if try_open(candidate):
                    LOGGER.info('Opened HDMI-CEC device %s (source=autodetect)', candidate)
                    return candidate, 'autodetect'

        LOGGER.error('CEC autodetect failed: no detected port could be opened (last=%s, candidates=%d)', last, len(adapters))
        raise ConnectionError('Could not connect to CEC adapter')

    def _on_log_callback(self, level, _time, message):
        m = {
            cec.CEC_LOG_ERROR:   ("ERROR",   logging.ERROR),
            cec.CEC_LOG_WARNING: ("WARNING", logging.WARNING),
            cec.CEC_LOG_NOTICE:  ("NOTICE",  logging.INFO),
            cec.CEC_LOG_TRAFFIC: ("TRAFFIC", logging.DEBUG),
            cec.CEC_LOG_DEBUG:   ("DEBUG",   logging.DEBUG),
        }
        tag, py = m.get(level, ("DEBUG", logging.DEBUG))
        LOGGER.log(py, "libcec: [%s] %s", tag, message)

        if 'physical address is invalid' in message:
            self._set_cec_connected(False)
        elif 'CEC_TRANSMIT failed' in message and 'errno=64' in message:
            self._set_cec_connected(False)

        if self.refreshing:
            return
        
        # TV (0): power status changed from 'unknown' to 'on'
        match = re.search(
            r'\(([0-9a-fA-F])\): power status changed from \'.*\' to \'(.*)\'',
            message
        )
        if match:
            device = int(match.group(1), 16)
            power = match.group(2)
            self._publish_power(device, power)

    # key press callback
    def _on_key_press_callback(self, key, duration):
        LOGGER.debug('_on_key_press_callback %s %s', key, duration)
        return 0

    # command callback
    # https://github.com/Pulse-Eight/libcec/blob/master/include/cectypes.h

    def _on_command_callback(self, cmd):
        self._set_cec_connected(True)
        initiator = int(cmd[3:4], 16)
        destination = int(cmd[4:5], 16)
        opcode = int(cmd[6:8], 16)
        LOGGER.debug('_on_command_callback %02x %s %x -> %x %s',
                     opcode, self.cec_client.OpcodeToString(opcode), initiator,
                     destination, cmd)
        # Send raw command to mqtt
        self._mqtt_send('cec/rx', cmd[3:])

        if self.refreshing:
            return 0

        if opcode == cec.CEC_OPCODE_REPORT_POWER_STATUS:
            power = int(cmd[9:], 16)
            self._publish_power(initiator, self.cec_client.PowerStatusToString(power))
        elif opcode == cec.CEC_OPCODE_DEVICE_VENDOR_ID:
            vendor_id = int((cmd[9:]).replace(':', ''), base=16)
            self._mqtt_send(
                f'cec/device/{initiator}/vendor',
                self.cec_client.VendorIdToString(vendor_id)
            )
            
            # Some AVRs may announce wake-up on logical address 3,
            # while the actual power status is tracked on 5 (Audio System).
            if initiator == 3 and 5 in self.devices:
                LOGGER.debug(
                    'AVR announced vendor id on logical address 3; requesting power status for 5'
                )
                self.tx_command('8F', 5)
            elif initiator in self.devices:
                LOGGER.debug(
                    'Device %d announced vendor id; requesting power status',
                    initiator
                )
                self.tx_command('8F', initiator)
        elif opcode == cec.CEC_OPCODE_REPORT_PHYSICAL_ADDRESS:
            physical_address = int(cmd[9:14].replace(':', ''), 16)
            self._mqtt_send(f'cec/device/{initiator}/address', f'{physical_address:04x}')
        elif opcode == cec.CEC_OPCODE_REPORT_AUDIO_STATUS:
            self._publish_audio_status(int(cmd[9:], 16), notify=True)
        elif opcode == cec.CEC_OPCODE_SET_SYSTEM_AUDIO_MODE:
            if self._is_suppressed(5):
                return 0
        
            self._mqtt_send(
                'cec/device/5/power',
                'on' if int(cmd[9:], 16) == 1 else 'off',
            )

        return 0

    def power_on(self, device: int):
        """Power on the specified device."""
        LOGGER.debug('Power on device %d', device)
        self._suppress(device)
        self._mqtt_send(f'cec/device/{device}/power', 'on')
        self.cec_client.PowerOnDevices(device)

    def power_off(self, device: int):
        """Power off the specified device."""
        LOGGER.debug('Power off device %d', device)
        self._suppress(device)
        self._mqtt_send(f'cec/device/{device}/power', 'off')
        self.cec_client.StandbyDevices(device)

    def _volume_step(self, up: bool, amount=1, update=True):
        action = self.cec_client.VolumeUp if up else self.cec_client.VolumeDown
        direction = 'up' if up else 'down'
        fast = amount >= 10
    
        LOGGER.debug('Volume %s%s with %d', direction, ' fast' if fast else '', amount)
    
        for i in range(amount):
            if fast:
                action(i == amount - 1)
            else:
                action()
            time.sleep(0.1)
    
        if update:
            self.tx_command('71', 5)

    def volume_up(self, amount=1, update=True):
        """Increase the volume on the AVR."""
        self._volume_step(True, amount, update)

    def volume_down(self, amount=1, update=True):
        """Decrease the volume on the AVR."""
        self._volume_step(False, amount, update)

    def _set_mute(self, muted: bool):
        LOGGER.debug('%s AVR', 'Mute' if muted else 'Unmute')
        self._suppress("mute")
        self._mqtt_send('cec/audio/mute', 'on' if muted else 'off')
        if muted:
            self.cec_client.AudioMute()
        else:
            self.cec_client.AudioUnmute()
    
    def volume_mute(self):
        """Mute the volume on the AVR."""
        self._set_mute(True)

    def volume_unmute(self):
        """Unmute the volume on the AVR."""
        self._set_mute(False)

    def _percent_to_native(self, volume_percent: int) -> int:
        """Convert external 0..100 volume into AVR native scale."""
        volume_percent = max(0, min(100, int(volume_percent)))
        return int(math.ceil(volume_percent * self.volume_correction / 100.0))

    def _native_to_percent(self, volume_native: int) -> int:
        """Convert AVR native scale into external 0..100 volume."""
        volume_native = max(0, min(self.volume_correction, int(volume_native)))
    
        if self.volume_correction <= 0:
            return 0
    
        return int(round(volume_native * 100.0 / self.volume_correction))
    
    def _request_avr_volume(self, timeout: float = 0.8, retries: int = 3) -> Optional[int]:
        """Request AVR volume and return it in AVR native scale."""
        for _ in range(retries):
            self.volume_update.clear()
            self.tx_command('71', device=5)
    
            if self.volume_update.wait(timeout):
                _, volume_native = self.decode_volume(self.cec_client.AudioStatus())
                return volume_native
    
        return None
    
    def volume_set(self, requested_volume: int):
        """Set the volume to the AVR (last request wins)."""
        # Create a new token; any previous in-flight volume_set should stop.
        with self._volume_token_lock:
            self._volume_token += 1
            my_token = self._volume_token
        self.volume_update.set()

        def cancelled() -> bool:
            return my_token != self._volume_token
    
        requested_percent = max(0, min(100, int(requested_volume)))
        requested_native = self._percent_to_native(requested_percent)
        
        LOGGER.debug(
            'Set volume to %d%% (native target=%d)',
            requested_percent,
            requested_native,
        )
        self.setting_volume = True
    
        try:
            # 1) Initial read
            current = self._request_avr_volume(timeout=0.6, retries=3)
            if cancelled():
                return
            if current is None:
                LOGGER.warning('No AVR volume status response (0x7A)')
                return
    
            # 2) Correction passes: compute diff -> send ALL steps (with delay) -> verify -> repeat if needed
            max_passes = 5
            step_delay = 0.0
            settle_delay = 0.5
    
            for _pass in range(max_passes):
                if cancelled():
                    return
    
                diff = requested_native - current
                if diff == 0:
                    return
    
                step_up = diff > 0
                steps = abs(diff)
    
                LOGGER.debug(
                    'Pass %d/%d: current=%d target=%d diff=%d steps=%d',
                    _pass + 1, max_passes, current, requested_native, diff, steps
                )
    
                # Send EXACTLY `steps` hold-style commands in a single pass
                action = self.cec_client.VolumeUp if step_up else self.cec_client.VolumeDown
                
                for i in range(steps):
                    if cancelled():
                        return
                    action(i == steps - 1)
                    time.sleep(step_delay)
    
                # Let AVR catch up before querying status
                time.sleep(settle_delay)
                if cancelled():
                    return
    
                # Verify once after the batch
                current = self._request_avr_volume(timeout=0.6, retries=2)
                if cancelled():
                    return
    
                if current is None:
                    # Fallback to cached value if 0x7A didn't arrive
                    _, current = self.decode_volume(self.cec_client.AudioStatus())
    
            LOGGER.warning(
                'Volume set did not converge after %d passes (last=%d target=%d)',
                max_passes, current, requested_native
            )
    
        finally:
            # Do NOT clear setting_volume if a newer request started meanwhile.
            if my_token == self._volume_token:
                self.setting_volume = False

    def decode_volume(self, audio_status: int) -> tuple[bool, int]:
        """Decode CEC audio status into mute and AVR native volume."""
        mute = audio_status > 127
        volume_percent = audio_status - 128 if mute else audio_status
        volume_native = int(math.ceil(volume_percent * self.volume_correction / 100.0))
    
        LOGGER.debug(
            'Audio Status = %s -> Mute = %s, VolumePercent = %s, VolumeNative = %s',
            audio_status,
            mute,
            volume_percent,
            volume_native,
        )
        return mute, volume_native
    
    def tx_command(self, command: str, device: int | None = None):
        """Send a raw CEC command to the specified device."""
        full_command = command if device is None else f'{self.device_id * 16 + device:x}:{command}'

        LOGGER.debug('Sending %s', full_command)
        self.cec_client.Transmit(self.cec_client.CommandFromString(full_command))

    def refresh(self):
        """Refresh the audio status and power status."""
        # :TODO: This operation takes ~2 sec should it be done in separate thread?
        if self.setting_volume:
            return
    
        LOGGER.debug('Refreshing HDMI-CEC...')
        self.refreshing = True
        try:
            for device in self.devices:
                physical_address = self.cec_client.GetDevicePhysicalAddress(device)
                if physical_address == 0xFFFF:
                    continue
    
                self._set_cec_connected(True)
                power = self.cec_client.GetDevicePowerStatus(device)
                power_str = self.cec_client.PowerStatusToString(power)
                LOGGER.debug(
                    'device %d %04x %-12s power %d %s',
                    device,
                    physical_address,
                    self.cec_client.LogicalAddressToString(device),
                    power,
                    power_str,
                )
    
                self._publish_power(device, power_str)
    
            self._publish_audio_status(self.cec_client.AudioStatus())
        finally:
            self.refreshing = False

    def scan(self):
        """scan for devices on the HDMI CEC bus"""
        LOGGER.debug("requesting CEC bus information ...")
        self.refreshing = True
        try:
            for device in self.devices:
                physical_address = self.cec_client.GetDevicePhysicalAddress(device)
                if physical_address == 0xFFFF:
                    continue
    
                self._set_cec_connected(True)
                vendor_id = self.cec_client.GetDeviceVendorId(device)
                active = self.cec_client.IsActiveSource(device)
                cec_version = self.cec_client.GetDeviceCecVersion(device)
                power = self.cec_client.GetDevicePowerStatus(device)
                osd_name = self.cec_client.GetDeviceOSDName(device)
    
                self._mqtt_send(f'cec/device/{device}/type', self.cec_client.LogicalAddressToString(device))
                self._mqtt_send(f'cec/device/{device}/address', f'{physical_address:04x}')
                self._mqtt_send(f'cec/device/{device}/active', str(active))
                self._mqtt_send(f'cec/device/{device}/vendor', self.cec_client.VendorIdToString(vendor_id))
                self._mqtt_send(f'cec/device/{device}/osd', osd_name)
                self._mqtt_send(f'cec/device/{device}/cecver', self.cec_client.CecVersionToString(cec_version))
                self._publish_power(device, self.cec_client.PowerStatusToString(power))
    
            self._publish_audio_status(self.cec_client.AudioStatus())
        finally:
            self.refreshing = False
