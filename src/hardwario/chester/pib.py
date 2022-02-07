import logging
import hardwario.common.pib

logger = logging.getLogger(__name__)


def hw_variant_to_number(text):
    text = text.replace('CHESTER-M-', '')
    hw_variant = 0
    variant_order = 'ABCDGLSV'
    for c in text:
        index = variant_order.index(c)
        hw_variant |= 1 << index
    return hw_variant


class PIB(hardwario.common.pib.PIB):

    BLE_PASSKEY = {
        2: (0x50, '<16s')
    }

    def __init__(self, buf=None):
        super().__init__(version=2, buf=buf)

    def _update_family(self):
        self._size = self._default_size + 16

    def get_ble_passkey(self):
        return '%s' % self._unpack(self.BLE_PASSKEY).decode('ascii').rstrip('\0')

    def set_ble_passkey(self, value):
        self._pack(self.BLE_PASSKEY, value.encode())
