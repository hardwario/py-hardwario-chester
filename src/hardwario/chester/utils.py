import os
from os.path import join, exists, abspath, isfile, getsize
from loguru import logger


def find_hex(app_path, no_exception=False):
    out_path = join(abspath(app_path), 'build', 'zephyr')

    for name in ('merged.hex', 'zephyr.hex'):
        hex_path = join(out_path, name)
        if exists(hex_path) and isfile(hex_path) and getsize(hex_path) > 0:
            return hex_path

    if no_exception:
        return None

    raise Exception('No firmware found.')
