import re
from hardwario.common.pib import PIB as PIBCommon, PIBException


class PIB(PIBCommon):

    HW_VARIANT_LIST = [
        'CDGLS',
        'CGLS',
        'CGS',
        'CGV',
        'CS',
        'CV',
        'L',
        'BCDGLS',
        'BCGLS',
        'BCGS',
        'BCGV',
        'BCS',
        'BCV',
        'BL',
        'ACDGLS',
        'ACGLS',
        'ACGS',
        'ACGV',
        'ACS',
        'ACV',
        'AL',
    ]

    CLAIM_TOKEN = {
        2: (0x45, '33s')
    }
    BLE_PASSKEY = {
        2: (0x66, '17s')
    }

    def __init__(self, buf=None):
        super().__init__(version=2, buf=buf)

    def _update_family(self):
        self._size = self._default_size + 33 + 17

    def set_hw_variant(self, value):
        if value not in self.HW_VARIANT_LIST:
            raise PIBException('Bad Hardware variant not from list.')
        super().set_hw_variant(value)

    def get_claim_token(self):
        return self._unpack(self.CLAIM_TOKEN)

    def set_claim_token(self, value):
        if not re.match(r'^[\dabcdef]{32}$', value) and value != '':
            raise PIBException('Bad Claim token (32 hexadecimal characters).')
        self._pack(self.CLAIM_TOKEN, value)

    def get_ble_passkey(self):
        return self._unpack(self.BLE_PASSKEY)

    def set_ble_passkey(self, value):
        if not re.match(r'^[a-zA-Z0-9]{0,16}$', value):
            raise PIBException('Bad BLE passkey (max 16 characters).')

        self._pack(self.BLE_PASSKEY, value)

    def get_dict(self):
        payload = super().get_dict()
        payload['claim_token'] = self.get_claim_token()
        payload['ble_passkey'] = self.get_ble_passkey()
        return payload
