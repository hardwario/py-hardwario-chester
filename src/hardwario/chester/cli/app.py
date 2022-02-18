import logging
import re
import click
import sys
import json
from ..pib import PIB, PIBException
from ..nrfjprog import NRFJProg


logger = logging.getLogger(__name__)


@click.group(name='app')
@click.pass_context
def cli(ctx):
    '''Application SoC commands.'''
    pass


@cli.command('flash')
@click.argument('hex_file', metavar="HEX_FILE")
def command_flash(hex_file):
    '''Flash application firmware (preserves UICR area).'''
    prog = NRFJProg('app')
    prog.program(hex_file)


@cli.command('erase')
@click.option('--all', is_flag=True, help="Erase application firmware incl. UICR area.")
def command_erase(all):
    '''Erase application firmware w/o UICR area.'''
    prog = NRFJProg('app')
    if all:
        prog.erase_all()
    else:
        prog.erase_flash()


@cli.command('reset')
def command_reset():
    '''Reset application firmware.'''
    prog = NRFJProg('app')
    prog.reset()


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
def command_pib_read(out_json):
    '''Read HARDWARIO Product Information Block from UICR.'''

    prog = NRFJProg('app')
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
@click.pass_context
def command_pib_write(ctx, vendor_name, product_name, hw_variant, hw_revision, serial_number, claim_token, ble_passkey):
    '''Write HARDWARIO Product Information Block to UICR.'''
    logger.debug("command_pib_write: %s", (serial_number,
                 vendor_name, product_name, hw_revision, hw_variant, claim_token, ble_passkey))

    pib = ctx.obj['pib']
    buffer = pib.get_buffer()

    logger.debug('write uicr: %s', buffer.hex())

    prog = NRFJProg('app')
    prog.write_uicr(buffer)


@cli.group(name='uicr')
def group_uicr():
    '''UICR flash area.'''
    pass


@group_uicr.command('read')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.argument('file', type=click.File('wb'))
def command_uicr_read(format, file):
    '''Read generic UICR flash area to <FILE> or stdout.'''

    prog = NRFJProg('app')
    buffer = prog.read_uicr()

    if format == 'hex':
        file.write(buffer.hex().encode())

    elif format == 'bin':
        file.write(buffer)


@group_uicr.command('write')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.argument('file', type=click.File('rb'))
def command_uicr_write(format, file):
    '''Write generic UICR flash area from <FILE> or stdout.'''

    buffer = file.read()

    if buffer and format == 'hex':
        buffer = bytes.fromhex((''.join(buffer.decode())).strip())

    if buffer is None:
        raise click.BadParameter('Problem load buffer.')

    if len(buffer) > 128:
        raise click.BadParameter('Buffer has wrong size allowed is max 128B')

    logger.debug('write uicr: %s', buffer.hex())

    prog = NRFJProg('app')
    prog.write_uicr(buffer)


def main():
    cli()
