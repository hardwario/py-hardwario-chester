import logging
from pynrfjprog import HighLevel, APIError
from pynrfjprog.Parameters import *
from .pib import PIB

_api = None
logger = logging.getLogger(__name__)


class NRFJProgException(Exception):
    pass


class NRFJProg(HighLevel.DebugProbe):

    def __init__(self, jlin_sn=None, clock_speed=None, log=False, log_suffix=None):
        api = get_api()
        if jlin_sn is None:
            probes = api.get_connected_probes()
            if not probes:
                raise NRFJProgException('No J-Link found (check USB cable)')
            jlin_sn = probes[0]

        try:
            super().__init__(api, jlin_sn, clock_speed=clock_speed, log=log)
        except APIError.APIError as e:
            if e.err_code == APIError.NrfjprogdllErr.LOW_VOLTAGE:
                raise NRFJProgException(
                    'Detected low voltage on J-Link (check power supply and cable)')
            else:
                raise NRFJProgException(str(e))

    def erase_uicr(self):
        info = self.get_device_info()
        self.erase(EraseAction.ERASE_SECTOR_AND_UICR,
                   info.uicr_address, info.uicr_address + 32)

    def erase_all(self):
        self.erase(EraseAction.ERASE_ALL)

    def erase_flash(self):
        info = self.get_device_info()
        self.erase(EraseAction.ERASE_SECTOR,
                   info.code_address, (info.code_size // 32))

    def program(self, hex_path):
        program_options = ProgramOptions(
            verify=VerifyAction.VERIFY_NONE,
            erase_action=EraseAction.ERASE_SECTOR,
            qspi_erase_action=EraseAction.ERASE_NONE,
            reset=ResetAction.RESET_SYSTEM
        )
        super().program(hex_path, program_options)

    def write_uicr(self, buffer: bytes):
        info = self.get_device_info()
        self.erase_uicr()
        self.write(info.uicr_address + 0x80, buffer)

    def read_uicr(self):
        info = self.get_device_info()
        return self.read(info.uicr_address + 0x80, 128)


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
