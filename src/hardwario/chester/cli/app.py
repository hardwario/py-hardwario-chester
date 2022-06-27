import click
import os
import json
import sys
import string
from datetime import datetime
from loguru import logger
from ..pib import PIB, PIBException
from ..nrfjprog import NRFJProg, HighNRFJProg
from ..console import Console
from ..firmwareapi import FirmwareApi, DEFAULT_API_URL
from ..utils import find_hex, download_url


@click.group(name='app')
@click.option('--nrfjprog-log', is_flag=True, help='Enable nrfjprog log.')
@click.pass_context
def cli(ctx, nrfjprog_log):
    '''Application SoC commands.'''
    ctx.obj['prog'] = NRFJProg('app', log=nrfjprog_log)


def validate_hex_file(ctx, param, value):
    # print('validate_hex_file', ctx.obj, param.name, value)
    if len(value) == 32 and all(c in string.hexdigits for c in value):
        return download_url(f'https://firmware.hardwario.com/chester/{value}/hex', filename=f'{value}.hex')

    if os.path.exists(value):
        return value

    raise click.BadParameter(f'Path \'{value}\' does not exist.')


@cli.command('flash')
@click.option('--halt', is_flag=True, help='Halt program.')
@click.argument('hex_file', metavar='HEX_FILE_OR_ID', callback=validate_hex_file, default=find_hex('.', no_exception=True))
@click.pass_context
def command_flash(ctx, halt, hex_file):
    '''Flash application firmware (preserves UICR area).'''
    click.echo(f'File: {hex_file}')

    def progress(text, ctx={'len': 0}):
        if ctx['len']:
            click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
        if not text:
            return
        ctx['len'] = len(text)
        click.echo(text, nl=text == 'Successfully completed')

    with ctx.obj['prog'] as prog:
        prog.program(hex_file, halt, progress=progress)


@cli.command('erase')
@click.option('--all', is_flag=True, help='Erase application firmware incl. UICR area.')
@click.pass_context
def command_erase(ctx, all):
    '''Erase application firmware w/o UICR area.'''
    with ctx.obj['prog'] as prog:
        if all:
            prog.erase_all()
        else:
            prog.erase_flash()


@cli.command('reset')
@click.option('--halt', is_flag=True, help='Halt program.')
@click.pass_context
def command_reset(ctx, halt):
    '''Reset application firmware.'''
    with ctx.obj['prog'] as prog:
        prog.reset()
        if halt:
            prog.halt()


default_history_file = os.path.expanduser("~/.chester_history")
default_console_file = os.path.expanduser("~/.chester_console")


@cli.command('console')
@click.option('--reset', is_flag=True, help='Reset application firmware.')
@click.option('--latency', type=int, help='Latency for RTT readout in ms.', show_default=True, default=50)
@click.option('--history-file', type=click.Path(writable=True), show_default=True, default=default_history_file)
@click.option('--console-file', type=click.File('a', 'utf-8'), show_default=True, default=default_console_file)
@click.pass_context
def command_console(ctx, reset, latency, history_file, console_file):
    '''Start interactive console for shell and logging.'''
    logger.remove(2)  # Remove stderr logger

    with ctx.obj['prog'] as prog:
        if reset:
            prog.reset()
            prog.go()
        Console(prog, history_file, console_file, latency=latency)


def validate_pib_param(ctx, param, value):
    # print('validate_pib_param', ctx.obj, param.name, value)
    try:
        getattr(ctx.obj['pib'], f'set_{param.name}')(value)
    except PIBException as e:
        raise click.BadParameter(str(e))
    return value


@cli.group(name='pib')
@click.pass_context
def group_pib(ctx):
    '''HARDWARIO Product Information Block.'''
    ctx.obj['pib'] = PIB()
    pass


@group_pib.command('read')
@click.option('--json', 'out_json', is_flag=True, help='Output in JSON format.')
@click.pass_context
def command_pib_read(ctx, out_json):
    '''Read HARDWARIO Product Information Block from UICR.'''

    with ctx.obj['prog'] as prog:
        buffer = prog.read_uicr()

    pib = PIB(buffer)

    if out_json:
        click.echo(json.dumps(pib.get_dict()))
    else:
        click.echo(f'Vendor name: {pib.get_vendor_name()}')
        click.echo(f'Product name: {pib.get_product_name()}')
        click.echo(f'Hardware variant: {pib.get_hw_variant()}')
        click.echo(f'Hardware revision: {pib.get_hw_revision()}')
        click.echo(f'Serial number: {pib.get_serial_number()}')
        click.echo(f'Claim token: {pib.get_claim_token()}')
        click.echo(f'BLE passkey: {pib.get_ble_passkey()}')


@group_pib.command('write')
@click.option('--vendor-name', type=str, help='Vendor name (max 16 characters).', default='HARDWARIO', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--product-name', type=str, help='Product name (max 16 characters).', default='CHESTER-M', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--hw-variant', type=click.Choice(PIB.HW_VARIANT_LIST), help='Hardware variant.', default='', prompt='Hardware variant', show_default=True, callback=validate_pib_param)
@click.option('--hw-revision', type=str, help='Hardware revision in Rx.y format.', default='R3.2', prompt='Hardware revision', show_default=True, callback=validate_pib_param)
@click.option('--serial-number', type=str, help='Serial number in decimal format.', prompt=True, callback=validate_pib_param)
@click.option('--claim-token', type=str, help='Claim token for device self-registration (32 hexadecimal characters).', default='', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--ble-passkey', type=str, help='Bluetooth security passkey (max 16 characters).', default='123456', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--halt', is_flag=True, help='Halt program.')
@click.pass_context
def command_pib_write(ctx, vendor_name, product_name, hw_variant, hw_revision, serial_number, claim_token, ble_passkey, halt):
    '''Write HARDWARIO Product Information Block to UICR.'''
    logger.debug('command_pib_write: %s', (serial_number,
                 vendor_name, product_name, hw_revision, hw_variant, claim_token, ble_passkey))

    pib = ctx.obj['pib']
    buffer = pib.get_buffer()

    logger.debug('write uicr: %s', buffer.hex())

    with ctx.obj['prog'] as prog:
        prog.write_uicr(buffer, halt=halt)


@cli.group(name='uicr')
def group_uicr():
    '''UICR flash area.'''
    pass


@group_uicr.command('read')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.argument('file', type=click.File('wb'))
@click.pass_context
def command_uicr_read(ctx, format, file):
    '''Read generic UICR flash area to <FILE> or stdout.'''

    with ctx.obj['prog'] as prog:
        buffer = prog.read_uicr()

    if format == 'hex':
        file.write(buffer.hex().encode())

    elif format == 'bin':
        file.write(buffer)


@group_uicr.command('write')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.option('--halt', is_flag=True, help='Halt program.')
@click.argument('file', type=click.File('rb'))
@click.pass_context
def command_uicr_write(ctx, format, halt, file):
    '''Write generic UICR flash area from <FILE> or stdout.'''

    buffer = file.read()

    if buffer and format == 'hex':
        buffer = bytes.fromhex((''.join(buffer.decode())).strip())

    if buffer is None:
        raise click.BadParameter('Problem load buffer.')

    if len(buffer) > 128:
        raise click.BadParameter('Buffer has wrong size allowed is max 128B')

    logger.debug('write uicr: %s', buffer.hex())

    with ctx.obj['prog'] as prog:
        prog.write_uicr(buffer, halt=halt)


@cli.group(name='fw')
@click.option('--url', metavar='URL', required=True, default=os.environ.get('HARDWARIO_FW_API_URL', DEFAULT_API_URL), show_default=True)
@click.option('--token', metavar='TOKEN', required='--help' not in sys.argv, envvar='HARDWARIO_CLOUD_TOKEN')
@click.pass_context
def cli_fw(ctx, url, token):
    '''Firmware commands.'''
    ctx.obj['fwapi'] = FirmwareApi(url=url, token=token)


@cli_fw.command('upload')
@click.option('--label', type=str, help='Firmware label (max 100 characters).', prompt=True, required=True)
@click.pass_context
def command_fw_upload(ctx, label):
    '''Upload application firmware.'''
    fw = ctx.obj['fwapi'].upload(label, '.')
    click.echo(f'UUID: {fw["id"]}')
    click.echo(f'URL: https://firmware.hardwario.com/chester/{fw["id"]}')


@cli_fw.command('list')
@click.option('--limit', type=click.IntRange(0, 100, clamp=True))
@click.pass_context
def command_fw_upload(ctx, limit):
    '''List application firmwares.'''
    click.echo(f'{"UUID":32} {"Time":19} Label')
    for fw in ctx.obj['fwapi'].list(limit=limit):
        dt = datetime.fromtimestamp(fw['timestamp'])
        click.echo(f'{fw["id"]} {dt} {fw["label"]}')


@cli_fw.command('delete')
@click.option('--id', metavar="ID", required=True)
@click.confirmation_option(prompt='Are you sure you want to delete firmware ?')
@click.pass_context
def command_fw_delete(ctx, id):
    '''Delete firmware.'''
    fw = ctx.obj['fwapi'].delete(id)
    click.echo('OK')


@cli_fw.command('show')
@click.option('--id', metavar="ID", show_default=True, required=True)
@click.pass_context
def command_fw_show(ctx, id):
    '''Show codec detail.'''
    fw = ctx.obj['fwapi'].detail(id)
    click.echo(f'UUID: {fw["id"]}')
    click.echo(f'URL: https://firmware.hardwario.com/chester/{fw["id"]}')
    click.echo(f'Label: {fw["label"]}')
    click.echo(f'Time: {datetime.fromtimestamp(fw["timestamp"])}')
    click.echo(f'Revision: {fw["revision"]}')
    click.echo(f'SHA256 firmware: {fw["firmware_sha256"]}')
    click.echo(f'SHA256 app_update: {fw["app_update_sha256"]}')
    click.echo(f'Build Manifest: {json.dumps(fw["manifest"])}')


def main():
    cli()
