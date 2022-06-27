import requests
import subprocess
from loguru import logger
from .utils import find_hex, test_file
from hardwario.common.util import get_file_hash

# DEFAULT_API_URL = 'http://0.0.0.0:4000/chester/api'
DEFAULT_API_URL = 'https://firmware.hardwario.com/chester/api'


class FirmwareApiException(Exception):
    pass


class FirmwareApi:

    def __init__(self, url=DEFAULT_API_URL, token=None):
        self._headers = {}
        self._url = url
        if token:
            self.set_token(token)

    def set_token(self, token):
        self._headers['Authorization'] = 'Bearer ' + token

    def request(self, method, url, **kwargs):
        url = self._url + url
        logger.debug('{} {}', url, kwargs)
        try:
            self._response = requests.request(
                method, url, headers=self._headers, **kwargs)
        except ConnectionError:
            raise FirmwareApiException('Cannot connect to cloud service')

        if 200 < self._response.status_code >= 300:
            text = self._response.text.strip('"')
            raise FirmwareApiException(f'{self._response.status_code}: {text}')

        return self._response.json()

    def upload(self, label, app_path='.'):
        logger.debug(f'label={label}')

        revision = None
        try:
            revision = subprocess.check_output(
                ['git', '-C', app_path, 'rev-parse', 'HEAD']).decode('ascii').strip()
        except Exception:
            pass

        data = {
            'label': label,
            'revision': revision
        }

        files = {}

        hex_path = find_hex(app_path)
        logger.debug(f'hex_path={hex_path}')

        data['firmware_sha256'] = get_file_hash(hex_path)
        files['firmware_hex'] = open(hex_path, 'rb')

        app_update_path = test_file(app_path, 'build', 'zephyr', 'app_update.bin')
        logger.debug(f'app_update_path={app_update_path}')
        if app_update_path:
            data['app_update_sha256'] = get_file_hash(app_update_path)
            files['app_update_bin'] = open(app_update_path, 'rb')

        manifest_json_path = test_file(app_path, 'build', 'zephyr', 'dfu_application.zip_manifest.json')
        logger.debug(f'manifest_json_path={manifest_json_path}')

        if manifest_json_path:
            files['manifest'] = open(manifest_json_path, 'rb')

        resp = self.request('POST', '/v1/firmware', data=data, files=files)
        logger.debug(f'Response {resp}')
        return resp

    def list(self, offset: int = 0, limit: int = None):
        return self._list('/v1/firmware', {}, offset, limit)

    def detail(self, id):
        return self.request('GET', f'/v1/firmware/{id}')

    def delete(self, id):
        return self.request('DELETE', f'/v1/firmware/{id}')

    def _list(self, url, params: dict, offset=0, limit=None):
        cnt = 0
        params['offset'] = offset

        while True:
            params['limit'] = 100 if limit is None else limit

            for row in self.request('GET', url, params=params):
                cnt += 1
                yield row

            if limit is not None and limit >= cnt:
                break

            x_total = int(self._response.headers['x-total'])
            params['offset'] = offset + cnt

            if params['offset'] >= x_total:
                break
