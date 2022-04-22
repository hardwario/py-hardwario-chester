from loguru import logger
from pynrfjprog import HighLevel, APIError, LowLevel
from pynrfjprog.Parameters import *
from .pib import PIB

_api = None


class NRFJProgException(Exception):
    pass


class NRFJProgRTTNoChannels(NRFJProgException):
    pass


class NRFJProg(LowLevel.API):
    def __init__(self, mcu, jlin_sn=None, clock_speed=None, log=False, log_suffix=None):
        self.mcu = mcu
        self.jlin_sn = jlin_sn
        self.clock_speed = clock_speed
        self.log = log
        self.log_suffix = log_suffix
        self._rtt_channels = None

    def open(self):
        try:
            super().__init__(LowLevel.DeviceFamily.UNKNOWN, log=self.log)
            super().open()

            if self.jlin_sn is not None:
                self.connect_to_emu_with_snr(self.jlin_sn)
            else:
                self.connect_to_emu_without_snr()

        except APIError.APIError as e:
            if e.err_code == APIError.NrfjprogdllErr.NO_EMULATOR_CONNECTED:
                raise NRFJProgException(
                    'No J-Link found (check USB cable)')
            if e.err_code == APIError.NrfjprogdllErr.LOW_VOLTAGE:
                raise NRFJProgException(
                    'Detected low voltage on J-Link (check power supply and cable)')
            raise NRFJProgException(str(e))

        device_family = self.read_device_family()

        if self.mcu == 'app':
            if device_family != 'NRF52':
                raise NRFJProgException(
                    'Detected bad MCU expect: app (NRF52)')
        elif self.mcu == 'lte':
            if device_family != 'NRF91':
                raise NRFJProgException(
                    'Detected bad MCU expect: lte (NRF91)')
        else:
            raise NRFJProgException(
                f'Unknown MCU family ({device_family}).')

        self.select_family(device_family)

        # print(self.read_device_info())

    def close(self):
        super().close()

    def reset(self):
        self.sys_reset()

    def erase_flash(self):
        self.disable_bprot()
        for des in self.read_memory_descriptors(False):
            if des.type == MemoryType.CODE:
                page_size = des.size // des.num_pages
                for addr in range(0, des.size, page_size):
                    self.erase_page(addr)

    def program(self, file_path, halt=False, progress=lambda x: None):
        progress('Erasing...')
        self.erase_file(file_path, chip_erase_mode=EraseAction.ERASE_SECTOR)

        progress('Flashing...')
        self.program_file(file_path)

        progress('Verifying...')
        self.verify_file(file_path)

        if halt:
            progress('Resetting (HALT)...')
            self.reset()
            self.halt()
        else:
            progress('Resetting (GO)...')
            self.reset()
            self.go()

        progress('Successfully completed')

    def get_uicr_address(self):
        for des in self.read_memory_descriptors(False):
            if des.type == MemoryType.UICR:
                return des.start
        raise NRFJProgException('UICR descriptor not found.')

    def write_uicr(self, buffer: bytes):
        self.erase_uicr()
        self.write(self.get_uicr_address() + 0x80, buffer, True)

    def read_uicr(self):
        return bytes(self.read(self.get_uicr_address() + 0x80, 128))

    def rtt_start(self):
        if self._rtt_channels is not None:
            return

        super().rtt_start()
        logger.debug('RTT Start')

        for _ in range(100):
            if self.rtt_is_control_block_found():
                logger.debug('RTT control block found')
                break
            time.sleep(0.1)
        else:
            raise NRFJProgException('Can not found RTT start block')

        channel_count = self.rtt_read_channel_count()
        logger.debug(f'RTT channel count {channel_count}')

        channels = {}
        for index in range(channel_count[0]):
            name, size = self.rtt_read_channel_info(index, RTTChannelDirection.DOWN_DIRECTION)
            if size < 1:
                continue
            channels[name] = {
                'down': {
                    'index': index,
                    'size': size
                }
            }
        for index in range(channel_count[1]):
            name, size = self.rtt_read_channel_info(index, RTTChannelDirection.UP_DIRECTION)
            if size < 1:
                continue
            if name not in channels:
                channels[name] = {}
            channels[name]['up'] = {
                'index': index,
                'size': size
            }

        self._rtt_channels = channels
        return self._rtt_channels

    def rtt_stop(self):
        if self._rtt_channels is None:
            return

        # super().rtt_stop() #  WHY: if call rtt_stop then Can not found RTT start block after rtt_start, needs reset for work
        self._rtt_channels = None
        logger.debug('RTT Stop')

    def rtt_is_running(self):
        return self._rtt_channels is not None

    def rtt_write(self, channel, msg, encoding='utf-8'):
        if self._rtt_channels is None:
            raise NRFJProgRTTNoChannels('Can not write, try call rtt_start first')
        if isinstance(channel, str):
            channel = self._rtt_channels[channel]['down']['index']
        logger.debug('channel: {} msg: {}', channel, repr(msg))
        return super().rtt_write(channel, msg, encoding)

    def rtt_read(self, channel, length=None, encoding='utf-8', ):
        if self._rtt_channels is None:
            raise NRFJProgRTTNoChannels('Can not read, try call rtt_start first')
        if isinstance(channel, str):
            ch = self._rtt_channels[channel]['up']
            if length is None:
                length = ch['size']
            channel = ch['index']
        msg = super().rtt_read(channel, length, encoding)
        if msg:
            logger.debug('channel: {} msg: {}', channel, repr(msg))
        return msg

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()


class HighNRFJProg(HighLevel.DebugProbe):

    def __init__(self, mcu, jlin_sn=None, clock_speed=None, log=False, log_suffix=None):
        self.mcu = mcu
        self.jlin_sn = jlin_sn
        self.clock_speed = clock_speed
        self.log = log
        self.log_suffix = log_suffix

    def open(self):
        jlin_sn = self.jlin_sn
        api = get_api()
        if jlin_sn is None:
            probes = api.get_connected_probes()
            if not probes:
                raise NRFJProgException('No J-Link found (check USB cable)')
            jlin_sn = probes[0]

        try:
            super().__init__(api, jlin_sn, clock_speed=self.clock_speed, log=self.log)
        except APIError.APIError as e:
            if e.err_code == APIError.NrfjprogdllErr.LOW_VOLTAGE:
                raise NRFJProgException(
                    'Detected low voltage on J-Link (check power supply and cable)')
            else:
                raise NRFJProgException(str(e))

        self.info = self.get_device_info()
        # print(self.info.__dict__)

        if self.mcu == 'app':
            if self.info.device_family != DeviceFamily.NRF52:
                raise NRFJProgException(
                    'Detected bad MCU expect: app (NRF52)')
        elif self.mcu == 'lte':
            if self.info.device_family != DeviceFamily.NRF91:
                raise NRFJProgException(
                    'Detected bad MCU expect: lte (NRF91)')
        else:
            raise NRFJProgException(
                f'Unknown MCU family ({self.info.device_family})')

    def erase_uicr(self):
        self.erase(EraseAction.ERASE_SECTOR_AND_UICR,
                   self.info.uicr_address, self.info.uicr_address + 32)

    def erase_all(self):
        self.erase(EraseAction.ERASE_ALL)

    def erase_flash(self):
        self.erase(EraseAction.ERASE_SECTOR,
                   self.info.code_address, (self.info.code_size // 32))

    def program(self, hex_path):
        program_options = ProgramOptions(
            verify=VerifyAction.VERIFY_READ,
            erase_action=EraseAction.ERASE_SECTOR,
            qspi_erase_action=EraseAction.ERASE_NONE,
            reset=ResetAction.RESET_SYSTEM
        )
        super().program(hex_path, program_options)

    def write_uicr(self, buffer: bytes):
        self.erase_uicr()
        self.write(self.info.uicr_address + 0x80, buffer)

    def read_uicr(self):
        return self.read(self.info.uicr_address + 0x80, 128)


def get_api():
    global _api
    if _api is None:
        api = HighLevel.API(True)
        api.open()
        _api = api
    return _api


def get_probe(jlin_sn=None):
    api = get_api()
    if not jlin_sn:
        probes = api.get_connected_probes()
        if not probes:
            raise NRFJProgException('No J-Link found (check USB cable)')
        jlin_sn = probes[0]

    try:
        probe = HighLevel.DebugProbe(get_api(), jlin_sn, log=False)
        return probe
    except APIError.APIError as e:
        if e.err_code == APIError.NrfjprogdllErr.LOW_VOLTAGE:
            raise NRFJProgException(
                'Detected low voltage on J-Link (check power supply and cable)')
        else:
            raise NRFJProgException(str(e))


# https://www.segger.com/downloads/jlink/JLink_Linux_x86_64.deb
# https://www.segger.com/downloads/jlink/JLink_Linux_arm.tgz
# https://www.segger.com/downloads/jlink
# {'device_type': < DeviceVersion.NRF52840_xxAA_REV2: 86523907 > , 'device_family': < DeviceFamily.NRF52: 1 > , 'code_address': 0, 'code_page_size': 4096, 'code_size': 1048576, 'uicr_address': 268439552, 'info_page_size': 4096, 'code_ram_present': True, 'code_ram_address': 8388608, 'data_ram_address': 536870912, 'ram_size': 262144, 'qspi_present': True, 'xip_address': 301989888, 'xip_size': 0, 'pin_reset_pin': 18, 'dll_ret_code': 0}
