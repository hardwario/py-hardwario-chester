import time
import os
import re
from .utils import join_path
from .nrfjprog import NRFJProg


class App:
    def __init__(self, prog: NRFJProg):
        self._prog = prog
        self._read_data = {'Terminal': '', 'Logger': ''}

        if not self._prog.is_opened:
            raise Exception('Open the device first')

    def _rtt_start(self):
        if self._prog.rtt_is_running():
            return

        channels = self._prog.rtt_start()

        if 'Terminal' not in channels:
            raise Exception('Not found RTT Terminal channel')

        if 'Logger' not in channels:
            raise Exception('Not found RTT Logger channel')

        # Clear the read data
        while line := self.terminal_read_line(0.2):
            pass

    def reset(self, go=True):
        for k in self._read_data:
            self._read_data[k] = ''
        self._prog.reset()
        if go:
            self._prog.go()

    def terminal_read_line(self, timeout):
        self._rtt_start()
        return self._rtt_read_line('Terminal', timeout)

    def terminal_write(self, data):
        self._rtt_start()
        self._prog.rtt_write('Terminal', data)

    def logger_read_line(self, timeout):
        self._rtt_start()
        return self._rtt_read_line('Logger', timeout)

    def _rtt_read_line(self, channel, timeout):
        c = self._read_data[channel]
        i = c.find('\n')
        if i > -1:
            line = c[:i]
            self._read_data[channel] = c[i + 1:]
            return line.rstrip()

        timeout = time.time() + timeout
        while time.time() < timeout:

            data = self._prog.rtt_read(channel)
            if data:
                self._read_data[channel] += data

            c = self._read_data[channel]
            i = c.find('\n')
            if i < 0:
                continue
            line = c[:i]
            self._read_data[channel] = c[i + 1:]
            return line.rstrip()

    def fs_ls(self, path: str = ''):
        self.terminal_write(f'fs ls {path}\n')
        lines = []
        while True:
            line = self.terminal_read_line(0.5)
            if not line:
                break
            lines.append(line)
        return lines

    def fs_stat(self, mount_point='/lfs1'):
        self.terminal_write(f'fs statvfs {mount_point}\n')
        line = self.terminal_read_line(0.5)
        if not line:
            raise Exception('Timeout waiting on response')
        m = re.match(r'bsize (\d+), frsize (\d+), blocks (\d+), bfree (\d+)', line)
        if not m:
            raise Exception(line)
        bsize = int(m.group(1))
        frsize = int(m.group(2))
        blocks = int(m.group(3))
        bfree = int(m.group(4))
        return {'size': frsize * blocks, 'free': frsize * bfree, 'used': frsize * (blocks - bfree)}

    def fs_mkdir(self, path: str):
        self.terminal_write(f'fs mkdir {path}\n')
        line = self.terminal_read_line(0.5)
        if line:
            raise Exception(line)

    def fs_download(self, src: str, dst: str, recursive: bool = False):
        if recursive:
            if os.path.isfile(dst):
                raise Exception(f'Destination {dst} is existing file')
            if not os.path.isdir(dst):
                os.makedirs(dst, exist_ok=True)

            ls = self.fs_ls(src)
            for f in ls:
                if f.endswith('/'):
                    self.fs_download(join_path(src, f), os.path.join(dst, f), recursive)
                else:
                    print(f'Copy {join_path(src, f)} -> {os.path.join(dst, f)}')
                    self.fs_read_file(join_path(src, f), os.path.join(dst, f))
        else:
            self.fs_read_file(src, dst)

    def fs_read_file(self, src: str, dst: str):
        if dst.endswith('/'):
            dst += os.path.basename(src)
        elif dst == '.':
            dst = os.path.basename(src)

        self.terminal_write(f'fs read {src}\n')
        while True:
            line = self.terminal_read_line(0.5)
            if not line:
                continue
            print(line)
            if 'File size' not in line:
                raise Exception(line)
            break
        with open(dst, 'wb') as f:
            while True:
                line = self.terminal_read_line(0.5)
                if not line:
                    break
                line = line.split('  ', 2)
                data = bytes.fromhex(line[1])
                f.write(data)

    def fs_upload(self, src, dst, recursive):
        if recursive:
            if not os.path.isdir(src):
                raise Exception(f'Source {src} is not a directory')

            try:
                self.fs_mkdir(join_path(dst, os.path.basename(src)))
            except Exception as e:
                pass

            for root, dirs, files in os.walk(src):
                for d in dirs:
                    try:
                        self.fs_mkdir(join_path(dst, root, d))
                    except Exception as e:
                        pass
                for f in files:
                    print(f'Copy {os.path.join(root, f)} -> {join_path(dst, root, f)}')
                    self.fs_write_file(os.path.join(root, f), join_path(dst, root, f))
        else:
            self.fs_write_file(src, dst)

    def fs_write_file(self, src, dst):
        if dst.endswith('/'):
            dst += os.path.basename(src)

        self.terminal_write(f'fs trunc {dst}\n')

        cmd = f'fs write {dst}'
        chunk_size = 17  # CONFIG_SHELL_ARGC_MAX=20
        with open(src, 'rb') as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                data_hex = ' '.join([f'{b:02X}' for b in data])
                self.terminal_write(f'{cmd} {data_hex}\n')
                time.sleep(0.02)
