import os
from os.path import join, exists, abspath, isfile, getsize, expanduser
import hashlib
import click
import requests
import binascii
from loguru import logger


DEFAULT_CACHE_PATH = expanduser("~/.hardwario/chester/cache")


def test_file(*paths):
    file_path = join(*paths)
    if exists(file_path) and isfile(file_path) and getsize(file_path) > 0:
        return file_path


def find_hex(app_path, no_exception=False):
    out_path = join(app_path, 'build', 'zephyr')

    for name in ('merged.hex', 'zephyr.hex'):
        hex_path = test_file(out_path, name)
        if hex_path:
            return hex_path

    if no_exception:
        return None

    raise Exception('No firmware found.')


def download_url(url, filename=None, cache_path=DEFAULT_CACHE_PATH):

    if not filename:
        if url.startswith("https://firmware.hardwario.com/chester"):
            filename = url[39:].replace('/', '.')
        else:
            filename = hashlib.sha256(url.encode()).hexdigest()

    if cache_path:
        os.makedirs(cache_path, exist_ok=True)
        filename = join(cache_path, filename)
        if os.path.exists(filename):
            return filename

    response = requests.get(url, stream=True, allow_redirects=True)
    if response.status_code != 200:
        raise Exception(response.text)
    total_length = response.headers.get('content-length')
    with open(filename, "wb") as f:
        if total_length is None:  # no content length header
            f.write(response.content)
        else:
            with click.progressbar(length=int(total_length), label='Download ') as bar:
                dl = 0
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    bar.update(dl)
    return filename


COREDUMP_PREFIX_STR = "#CD:"
COREDUMP_BEGIN_STR = COREDUMP_PREFIX_STR + "BEGIN#"
COREDUMP_END_STR = COREDUMP_PREFIX_STR + "END#"
COREDUMP_ERROR_STR = COREDUMP_PREFIX_STR + "ERROR CANNOT DUMP#"


class Coredump:
    def __init__(self):
        self.has_begin = False
        self.has_end = False
        self.has_error = False
        self.data = b''

    def feed_line(self, line: str):
        line = line.strip()
        if not line:
            return

        if line.find(COREDUMP_BEGIN_STR) >= 0:
            self.has_begin = True
            self.data = b''
            return

        elif line.find(COREDUMP_END_STR) >= 0:
            self.has_end = True
            return

        elif line.find(COREDUMP_ERROR_STR) >= 0:
            self.has_error = True
            return

        if not self.has_begin:
            return

        prefix_idx = line.find(COREDUMP_PREFIX_STR)
        if prefix_idx < 0:
            self.has_end = True
            self.has_error = True
            return

        if self.has_end:
            raise Exception("Coredump already finished")

        hex_str = line[prefix_idx + len(COREDUMP_PREFIX_STR):]

        try:
            self.data += binascii.unhexlify(hex_str)
        except Exception as e:
            logger.error("Cannot parse coredump hex_str: {}".format(hex_str))
            self.has_error = True
            self.has_end = True

    def reset(self):
        self.has_begin = False
        self.has_end = False
        self.has_error = False
        self.data = b''
