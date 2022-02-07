import logging
import hardwario.common.pib

logger = logging.getLogger(__name__)


class PIB(hardwario.common.pib.PIB):

    CLAIM_TOKEN = {
        2: (0x46, '33s')
    }
    BLE_PASSKEY = {
        2: (0x67, '17s')
    }

    def __init__(self, buf=None):
        super().__init__(version=2, buf=buf)

    def _update_family(self):
        self._size = self._default_size + 33 + 17

    def get_claim_token(self):
        return self._unpack(self.CLAIM_TOKEN)

    def set_claim_token(self, value):
        self._pack(self.CLAIM_TOKEN, value)

    def get_ble_passkey(self):
        return self._unpack(self.BLE_PASSKEY)

    def set_ble_passkey(self, value):
        self._pack(self.BLE_PASSKEY, value)

    def get_dict(self):
        payload = super().get_dict()
        payload['claim_token'] = self.get_claim_token()
        payload['ble_passkey'] = self.get_ble_passkey()
        return payload
