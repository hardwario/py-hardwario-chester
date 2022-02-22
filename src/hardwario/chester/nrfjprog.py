import logging
from pynrfjprog import HighLevel, APIError, LowLevel
from pynrfjprog.Parameters import *
from .pib import PIB

_api = None
logger = logging.getLogger(__name__)


class NRFJProgException(Exception):
    pass


class NRFJProg(HighLevel.DebugProbe):

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

        if self.mcu == 'app':
            if self.info.device_family != DeviceFamily.NRF52:
                raise NRFJProgException(
                    'Detected bad MCU expect: app (NRF52).')
        elif self.mcu == 'lte':
            if self.info.device_family != DeviceFamily.NRF91:
                raise NRFJProgException(
                    'Detected bad MCU expect: lte (NRF91).')
        else:
            raise NRFJProgException(
                f'Unknown MCU family ({self.info.device_family}).')

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
