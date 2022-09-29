import os
from loguru import logger
import docker
import sys


def find_west_config_path(path='.', max_deep=5):
    path = os.path.abspath(path)
    for _ in range(max_deep):
        config_path = os.path.join(path, '.west', 'config')
        if os.path.exists(config_path) and os.path.isfile(config_path):
            return config_path
        path = os.path.abspath(os.path.join(path, '..'))


def find_zephyr_base(path):
    config_path = find_west_config_path(path)
    if config_path:
        return os.path.abspath(os.path.join(config_path, '..', '..'))


def exec(command, app_path, image):
    app_path = os.path.abspath(app_path)
    west_path = find_zephyr_base(app_path)

    kwargs = {
        'image': image,
        'command': command,
        'detach': False,
        'working_dir': app_path,
        'user': os.getuid(),
        'volumes': {
            west_path: {'bind': west_path, 'mode': 'rw'},
            # '/tmp/ccache': {'bind': '/var/cache/ccache', 'mode': 'rw'}
        }
    }

    logger.debug(f'container args {kwargs}')

    client = docker.from_env()
    try:
        container = client.containers.create(**kwargs)
    except docker.errors.ImageNotFound:
        client.images.pull(image, platform=None)
        container = client.containers.create(**kwargs)

    container.start()

    for line in container.logs(stream=True, follow=True):
        print(line.decode('utf-8').strip())
    exit_status = container.wait()['StatusCode']
    if exit_status != 0:
        raise Exception(f'Faild {command}')


def build(app_path):
    # image = "hardwario/nrf-connect-sdk-build:latest"
    image = "test"
    print(exec('west build', app_path, image))
