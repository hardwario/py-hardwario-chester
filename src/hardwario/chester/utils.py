import os
from os.path import join, exists, abspath, isfile, getsize, expanduser
import hashlib
import click
import requests
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
