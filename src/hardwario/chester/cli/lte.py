import click
import tempfile
import zipfile
import os
import socket
import time
from loguru import logger
from ..pib import PIB, PIBException
from ..nrfjprog import NRFJProg, DEFAULT_JLINK_SPEED_KHZ


@click.group(name='lte')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.option('--nrfjprog-log', is_flag=True, help='Enable NRFJProg log.')
@click.pass_context
def cli(ctx, jlink_sn, jlink_speed, nrfjprog_log):
    '''LTE Modem SoC commands.'''
    ctx.obj['prog'] = NRFJProg('lte', log=nrfjprog_log, jlink_sn=jlink_sn, jlink_speed=jlink_speed)


@cli.command('flash')
@click.argument('file', metavar='FILE', type=click.Path(exists=True))
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_flash(ctx, jlink_sn, jlink_speed, file):
    '''Flash modem firmware.'''

    def progress(text, ctx={'len': 0}):
        if ctx['len']:
            click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
        if not text:
            return
        text = f'  {text}'
        ctx['len'] = len(text)
        click.echo(text, nl=text == 'Successfully completed')

    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)

    if file.endswith('.zip'):
        zf = zipfile.ZipFile(file)
        namelist = zf.namelist()
        if len(namelist) == 2:
            if 'modem.zip' not in namelist or 'application.hex' not in namelist:
                raise Exception('Invalid file.')

            with tempfile.TemporaryDirectory() as temp_dir:
                zf.extractall(temp_dir)
                with ctx.obj['prog'] as prog:
                    click.echo(f'Flash: modem.zip')
                    prog.program(os.path.join(temp_dir, 'modem.zip'), progress=progress)
                    progress(None)
                    click.echo(f'Flash: application.hex')
                    prog.program(os.path.join(temp_dir, 'application.hex'), progress=progress)
    else:
        with ctx.obj['prog'] as prog:
            click.echo(f'Flash: {file}')
            prog.program(file, progress=progress)

    progress(None)
    click.echo('Successfully completed')


@cli.command('erase')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_erase(ctx, jlink_sn, jlink_speed):
    '''Erase modem firmware.'''
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)
    with ctx.obj['prog'] as prog:
        prog.erase_all()
    click.echo('Successfully completed')


@cli.command('reset')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_reset(ctx, jlink_sn, jlink_speed):
    '''Reset modem firmware.'''
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)
    with ctx.obj['prog'] as prog:
        prog.reset()
    click.echo('Successfully completed')


@cli.command('trace')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.option('--file', '-f', 'filename', metavar='FILE', type=click.Path(writable=True))
@click.option('--tcp', '-t', 'tcpconnect', metavar='TCP', type=str, help='TCP connect to server, format: <host>:<port>')
@click.pass_context
def command_trace(ctx, jlink_sn, jlink_speed, filename, tcpconnect):
    '''Reset modem firmware.'''

    # sudo socat -d -d pty,link=/dev/virtual_serial_port,raw,echo=0,group-late=dialout,perm=0777 TCP-LISTEN:5555,reuseaddr,fork

    if jlink_sn:
        ctx.obj['prog'].set_serial_number(jlink_sn)

    if jlink_speed != DEFAULT_JLINK_SPEED_KHZ:
        ctx.obj['prog'].set_speed(jlink_speed)

    fd = None
    client_socket = None

    if filename:
        fd = open(filename, 'wb')

    if tcpconnect:
        host, port = tcpconnect.split(':')
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, int(port)))

    while True:
        print('Starting modem trace...')

        text_len = 0

        try:
            with ctx.obj['prog'] as prog:

                channels = prog.rtt_start()

                if 'modem_trace' not in channels:
                    raise Exception('Not found modem_trace channel in RTT.')

                print('Started modem trace')
                recv_len = 0
                text_len = 0

                e_cnt = 0
                while True:
                    try:
                        data = prog.rtt_read('modem_trace', encoding=None)
                    except Exception as e:
                        e_cnt += 1
                        if e_cnt > 10:
                            raise
                        continue

                    if fd:
                        fd.write(data)
                        fd.flush()

                    if client_socket:
                        try:
                            client_socket.send(data)
                        except Exception as e:
                            if text_len:
                                print()
                                text_len = 0
                            print(e)

                    if text_len:
                        print(('\b' * text_len) + (' ' * text_len) + ('\b' * text_len), end='')
                    if data:
                        recv_len += len(data)

                    last_text = f'Receive: {recv_len} B'
                    text_len = len(last_text)
                    print(last_text, end='')

        except Exception as e:
            if last_text:
                print()
            print('Restart exception:', str(e))
            time.sleep(0.5)


def main():
    cli()
