#!/usr/bin/env python3
"""HDMI CEC interface to HDMI CEC MQTT bridge"""

import logging
import math
import re
import threading
import time
from typing import Callable, List, Optional
import cec

SUPPRESS_S = 5.0

LOGGER = logging.getLogger(__name__)


class HdmiCec:
    """HDMI CEC interface class"""
    def __init__(
        self,
        port: str,
        name: str,
        devices: List[int],
        mqtt_send: Callable[..., None],
        volume_correction: Optional[int] = None,
    ):
        self._mqtt_send = mqtt_send
        self.devices = devices
        self.volume_correction = 1.0 if volume_correction is None else (volume_correction / 100.0)

        self.setting_volume = False
        self.refreshing = False
        self._suppress_until = {}
        self.volume_update = threading.Event()
        self._volume_token = 0
        self._volume_token_lock = threading.Lock()

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

        if not self.refreshing:
            # TV (0): power status changed from 'unknown' to 'on'
            match = re.search(
                r'\(([0-9a-fA-F])\): power status changed from \'.*\' to \'(.*)\'',
                message
            )
            if match:
                device = int(match.group(1), 16)
                power = match.group(2)
                mapped = self._ha_power(power)
        
                if time.monotonic() >= self._suppress_until.get(device, 0):
                    self._mqtt_send(f'cec/device/{device}/power', mapped)

    # key press callback
    def _on_key_press_callback(self, key, duration):
        LOGGER.debug('_on_key_press_callback %s %s', key, duration)
        return 0

    # command callback
    # https://github.com/Pulse-Eight/libcec/blob/master/include/cectypes.h
    # https://www.hdmi.org/docs/Hdmi13aSpecs

    def _on_command_callback(self, cmd):
        initiator = int(cmd[3:4], base=16)
        destination = int(cmd[4:5], base=16)
        opcode = int(cmd[6:8], base=16)
        LOGGER.debug('_on_command_callback %02x %s %x -> %x %s',
                     opcode, self.cec_client.OpcodeToString(opcode), initiator,
                     destination, cmd)
        # Send raw command to mqtt
        self._mqtt_send('cec/rx', cmd[3:])

        if not self.refreshing:
            if opcode == cec.CEC_OPCODE_REPORT_POWER_STATUS:
                power = int(cmd[9:], base=16)
                value = self._ha_power(self.cec_client.PowerStatusToString(power))
            
                if time.monotonic() < self._suppress_until.get(initiator, 0):
                    return 0
            
                self._mqtt_send(f'cec/device/{initiator}/power', value)
            elif opcode == cec.CEC_OPCODE_DEVICE_VENDOR_ID:
                vendor_id = int((cmd[9:]).replace(':',''), base=16)
                self._mqtt_send(f'cec/device/{initiator}/vendor',
                                self.cec_client.VendorIdToString(vendor_id))
            elif opcode == cec.CEC_OPCODE_REPORT_PHYSICAL_ADDRESS:
                physical_address = int((cmd[9:14]).replace(':',''), base=16)
                self._mqtt_send(f'cec/device/{initiator}/address',
                                 f'{physical_address:04x}')
            elif opcode == cec.CEC_OPCODE_REPORT_AUDIO_STATUS:
                mute, volume = self.decode_volume(int(cmd[9:], base=16))
                self._mqtt_send('cec/audio/volume', volume)
                if time.monotonic() >= self._suppress_until.get("mute", 0):
                    self._mqtt_send('cec/audio/mute', 'on' if mute else 'off')
                self.volume_update.set()
            elif opcode == cec.CEC_OPCODE_SET_SYSTEM_AUDIO_MODE:
                if time.monotonic() < self._suppress_until.get(5, 0):
                    return 0
            
                if int(cmd[9:], base=16) == 1:
                    self._mqtt_send('cec/device/5/power', 'on')
                else:
                    self._mqtt_send('cec/device/5/power', 'off')

        return 0

    def power_on(self, device: int):
        """Power on the specified device."""
        LOGGER.debug('Power on device %d', device)
        self._suppress_until[device] = time.monotonic() + SUPPRESS_S
        self._mqtt_send(f'cec/device/{device}/power', 'on')
        self.cec_client.PowerOnDevices(device)

    def power_off(self, device: int):
        """Power off the specified device."""
        LOGGER.debug('Power off device %d', device)
        self._suppress_until[device] = time.monotonic() + SUPPRESS_S
        self._mqtt_send(f'cec/device/{device}/power', 'off')
        self.cec_client.StandbyDevices(device)

    def volume_up(self, amount=1, update=True):
        """Increase the volume on the AVR."""
        if amount >= 10:
            LOGGER.debug('Volume up fast with %d', amount)
            for i in range(amount):
                self.cec_client.VolumeUp(i == amount - 1)
                time.sleep(0.1)
        else:
            LOGGER.debug('Volume up with %d', amount)
            for i in range(amount):
                self.cec_client.VolumeUp()
                time.sleep(0.1)

        if update:
            # Ask AVR to send us an update
            self.tx_command('71', 5)

    def volume_down(self, amount=1, update=True):
        """Decrease the volume on the AVR."""
        if amount >= 10:
            LOGGER.debug('Volume down fast with %d', amount)
            for i in range(amount):
                self.cec_client.VolumeDown(i == amount - 1)
                time.sleep(0.1)
        else:
            LOGGER.debug('Volume down with %d', amount)
            for i in range(amount):
                self.cec_client.VolumeDown()
                time.sleep(0.1)

        if update:
            # Ask AVR to send us an update
            self.tx_command('71', 5)

    def volume_mute(self):
        """Mute the volume on the AVR."""
        LOGGER.debug('Mute AVR')
        self._suppress_until["mute"] = time.monotonic() + SUPPRESS_S
        self._mqtt_send('cec/audio/mute', 'on')
        self.cec_client.AudioMute()

    def volume_unmute(self):
        """Unmute the volume on the AVR."""
        LOGGER.debug('Unmute AVR')
        self._suppress_until["mute"] = time.monotonic() + SUPPRESS_S
        self._mqtt_send('cec/audio/mute', 'off')
        self.cec_client.AudioUnmute()

    def _request_avr_volume(self, timeout: float = 0.8, retries: int = 3) -> Optional[int]:
        """Request AVR volume via Give Audio Status (0x71) and wait for Report Audio Status (0x7A)."""
        for _ in range(retries):
            self.volume_update.clear()
            self.tx_command('71', device=5)
    
            if self.volume_update.wait(timeout):
                _, v = self.decode_volume(self.cec_client.AudioStatus())
                return v
    
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
    
        LOGGER.debug('Set volume to %d', requested_volume)
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
            step_delay = 0.1
            settle_delay = 0.5
    
            for _pass in range(max_passes):
                if cancelled():
                    return
    
                diff = requested_volume - current
                if diff == 0:
                    return
    
                step_up = diff > 0
                steps = abs(diff)
    
                LOGGER.debug(
                    'Pass %d/%d: current=%d target=%d diff=%d steps=%d',
                    _pass + 1, max_passes, current, requested_volume, diff, steps
                )
    
                # Send EXACTLY `steps` clicks in a single pass, with a real delay between clicks
                for _ in range(steps):
                    if cancelled():
                        return
                    if step_up:
                        self.cec_client.VolumeUp()
                    else:
                        self.cec_client.VolumeDown()
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
                max_passes, current, requested_volume
            )
    
        finally:
            # Do NOT clear setting_volume if a newer request started meanwhile.
            if my_token == self._volume_token:
                self.setting_volume = False

    def decode_volume(self, audio_status) -> tuple[bool, int]:
        """Decodes CEC audio status into mute and real volume

        Args:
            audio_status (int): CEC audio status

        Returns:
            tuple[bool, int]: mute, real volume
        """
        mute = audio_status > 127
        volume = audio_status - 128 if mute else audio_status
        real_volume = int(math.ceil(volume * self.volume_correction))

        LOGGER.debug('Audio Status = %s -> Mute = %s, Volume = %s, Real Volume = %s',
                     audio_status, mute, volume, real_volume)
        return mute, real_volume

    def tx_command(self, command: str, device: int = None):
        """Send a raw CEC command to the specified device."""
        if device is None:
            full_command = command
        else:
            full_command = f'{self.device_id * 16 + device:x}:{command}'

        LOGGER.debug('Sending %s', full_command)
        self.cec_client.Transmit(self.cec_client.CommandFromString(full_command))

    def refresh(self):
        """Refresh the audio status and power status."""
        # :TODO: This operation takes ~2 sec should it be done in separate thread?
        if self.setting_volume:
            return
    
        LOGGER.debug('Refreshing HDMI-CEC...')
        self.refreshing = True
        for device in self.devices:
            # Get power status values of discovered devices from ceclib
            # This will setting unknown power state when device does not respond.
            physical_address = self.cec_client.GetDevicePhysicalAddress(device)
            if physical_address != 0xFFFF:
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
    
                mapped = self._ha_power(power_str)
                if time.monotonic() >= self._suppress_until.get(device, 0):
                    self._mqtt_send(f'cec/device/{device}/power', mapped)
    
        # Ask AVR to send us an audio status update
        mute, volume = self.decode_volume(self.cec_client.AudioStatus())
        self._mqtt_send('cec/audio/volume', volume)
        if time.monotonic() >= self._suppress_until.get("mute", 0):
            self._mqtt_send('cec/audio/mute', 'on' if mute else 'off')
        self.refreshing = False

    def scan(self):
        """scan for devices on the HDMI CEC bus"""
        LOGGER.debug("requesting CEC bus information ...")
        self.refreshing = True
        for device in self.devices:
            # Get power status values of discovered devices from ceclib
            # This will setting unknown power state when device does not respond.
            physical_address = self.cec_client.GetDevicePhysicalAddress(device)
            if physical_address != 0xFFFF:
                vendor_id   = self.cec_client.GetDeviceVendorId(device)
                active      = self.cec_client.IsActiveSource(device)
                cec_version = self.cec_client.GetDeviceCecVersion(device)
                power       = self.cec_client.GetDevicePowerStatus(device)
                osd_name    = self.cec_client.GetDeviceOSDName(device)

                self._mqtt_send(f'cec/device/{device}/type', self.cec_client.LogicalAddressToString(device))
                self._mqtt_send(f'cec/device/{device}/address', f'{physical_address:04x}')
                self._mqtt_send(f'cec/device/{device}/active', str(active))
                self._mqtt_send(f'cec/device/{device}/vendor', self.cec_client.VendorIdToString(vendor_id))
                self._mqtt_send(f'cec/device/{device}/osd', osd_name)
                self._mqtt_send(f'cec/device/{device}/cecver', self.cec_client.CecVersionToString(cec_version))
                mapped = self._ha_power(self.cec_client.PowerStatusToString(power))
                if time.monotonic() >= self._suppress_until.get(device, 0):
                    self._mqtt_send(f'cec/device/{device}/power', mapped)
        
        # Ask AVR to send us an audio status update
        mute, volume = self.decode_volume(self.cec_client.AudioStatus())
        self._mqtt_send('cec/audio/volume', volume)
        if time.monotonic() >= self._suppress_until.get("mute", 0):
            self._mqtt_send('cec/audio/mute', 'on' if mute else 'off')
        self.refreshing = False
