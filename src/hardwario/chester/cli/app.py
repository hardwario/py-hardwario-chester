import logging
import re
import click
import sys
import json
from ..pib import PIB
from ..nrfjprog import NRFJProg


logger = logging.getLogger(__name__)
hw_variant_list = [
    'BCDGLS',
    'BCGLS',
    'BCGS',
    'BCGV',
    'BCS',
    'BCV',
    'BL',
    'CGLS',
    'CGS',
    'CGV',
    'CS',
    'CV',
    'L'
]


@click.group(name='app')
@click.pass_context
def cli(ctx):
    '''Application SoC commands.'''
    pass


@cli.command('flash')
@click.argument('hex_file', metavar="HEX_FILE")
def command_flash(hex_file):
    '''Flash application firmware (preserves UICR area).'''
    prog = NRFJProg()
    prog.program(hex_file)


@cli.command('erase')
@click.option('--all', is_flag=True, help="Erase application firmware incl. UICR area.")
def command_erase(all):
    '''Erase application firmware w/o UICR area.'''
    prog = NRFJProg()
    if all:
        prog.erase_all()
    else:
        prog.erase_flash()


def validate_vendor_name(ctx, param, value):
    if len(value) > 15:
        raise click.BadParameter('Bad Vendor name (max 15 characters).')
    return value


def validate_product_name(ctx, param, value):
    if len(value) > 15:
        raise click.BadParameter('Bad Product name (max 15 characters).')
    return value


def validate_hw_variant(ctx, param, value):
    if value not in hw_variant_list:
        raise click.BadParameter('Bad Hardware variant not from options.')
    return value


def validate_hw_revision(ctx, param, value):
    m = re.match(r'^R(\d\d?)\.(\d\d?)$', str(value))
    if not m:
        raise click.BadParameter('Bad Hardware version format, expect: Rx.y .')
    return value


def validate_serial_number(ctx, param, value):
    if (int(value) & 0xc0000000) != 0x80000000:
        raise click.BadParameter('Bad serial number format')
    return value


def validate_ble_passkey(ctx, param, value):
    if len(value) > 15:
        raise click.BadParameter('Tool long BLE passkey, (max 16 characters).')
    return value


@cli.group(name='uicr')
def group_uicr():
    '''UICR flash area.'''
    pass


@group_uicr.command('read')
@click.option('--pib', 'output', flag_value='pib', required=True, help='Read HARDWARIO Product Information Block from UICR.')
@click.option('--pib-json', 'output', flag_value='pib-json', required=True, help='Read HARDWARIO Product Information Block from UICR to <FILE> or stdout.')
@click.option('--bin', 'output', flag_value='bin', required=True, help='Read generic UICR flash area to <FILE> or stdout.')
@click.option('--hex', 'output', flag_value='hex', required=True, help='Read generic UICR flash area to <FILE> or stdout.')
@click.argument('file', metavar="<FILE>", nargs=-1)
def command_uicr_read(output, file):
    if file:
        if len(file) != 1:
            raise click.BadParameter('Too many arguments.')
        file = file[0]

    prog = NRFJProg()
    buffer = prog.read_uicr()

    if output == 'pib':
        pib = PIB(buffer)
        print(f'Vendor name: {pib.get_vendor_name()}')
        print(f'Product name: {pib.get_product_name()}')
        print(f'Hardware variant: {pib.get_hw_variant()}')
        print(f'Hardware revision: {pib.get_hw_revision()}')
        print(f'Serial number: {pib.get_serial_number()}')
        print(f'Claim token: {pib.get_claim_token()}')
        print(f'BLE passkey: {pib.get_ble_passkey()}')

    if output == 'pib-json':
        pib = PIB(buffer)
        if file:
            with open(file, 'w') as fd:
                json.dump(pib.get_dict(), fd, indent=2)
        else:
            print(json.dumps(pib.get_dict()))

    elif output == 'hex':
        if file:
            with open(file, 'w') as fd:
                fd.write(buffer.hex())
        else:
            print(buffer.hex())

    elif output == 'bin':
        if file:
            with open(file, 'wb') as fd:
                fd.write(buffer)
        else:
            sys.stdout.buffer.write(buffer)


hw_variant_help = 'Hardware variant in hexadecimal format or one of the options: ' + \
    ('\n'.join(hw_variant_list))


@group_uicr.command('write')
@click.option('--pib', 'input', flag_value='pib', required=True, help='Write HARDWARIO Product Information Block to UICR.')
@click.option('--bin', 'input', flag_value='bin', required=True, help='Write generic UICR flash area from <FILE> or stdin.')
@click.option('--hex', 'input', flag_value='hex', required=True, help='Write generic UICR flash area from <FILE> or stdin.')
@click.option('--vendor-name', type=str, help='Vendor name (max 15 characters).', default='HARDWARIO', prompt='--pib' in sys.argv, show_default=True, callback=validate_vendor_name)
@click.option('--product-name', type=str, help='Product name (max 15 characters).', default='CHESTER-M', prompt='--pib' in sys.argv, show_default=True, callback=validate_product_name)
@click.option('--hw-variant', type=click.Choice(hw_variant_list), help='Hardware variant.', default='', prompt='Hardware variant' if '--pib' in sys.argv else False, show_default=True)
@click.option('--hw-revision', type=str, help='Hardware revision in Rx.y format.', default='R3.2', prompt='Hardware revision' if '--pib' in sys.argv else False, show_default=True, callback=validate_hw_revision)
@click.option('--serial-number', type=str, help='Serial number in decimal format.', prompt='--pib' in sys.argv, callback=validate_serial_number)
@click.option('--claim-token', type=str, help='Bluetooth security passkey (max 32 characters).', default='', prompt='--pib' in sys.argv, show_default=True, callback=validate_ble_passkey)
@click.option('--ble-passkey', type=str, help='Bluetooth security passkey (max 16 characters).', default='123456', prompt='--pib' in sys.argv, show_default=True, callback=validate_ble_passkey)
@click.argument('file', metavar="<FILE>", nargs=-1)
def command_uicr_write(input, vendor_name, product_name, hw_variant, hw_revision, serial_number, claim_token, ble_passkey, file):
    logger.debug("command_pib_write: %s", (input, serial_number,
                 vendor_name, product_name, hw_revision, hw_variant, claim_token, ble_passkey, file))
    if file:
        if len(file) != 1:
            raise click.BadParameter('Too many arguments.')
        file = file[0]

    buffer = None

    if input == 'pib':
        pib = PIB()
        pib.set_vendor_name(vendor_name)
        pib.set_product_name(product_name)
        pib.set_hw_revision(hw_revision)
        pib.set_hw_variant(hw_variant)
        pib.set_serial_number(serial_number)
        pib.set_claim_token(claim_token)
        pib.set_ble_passkey(ble_passkey)
        buffer = pib.get_buffer()

    elif input == 'hex':
        if file:
            with open(file, 'r') as fd:
                buffer = bytes.fromhex((''.join(fd.read())).strip())
        else:
            buffer = bytes.fromhex((''.join(sys.stdin.readline())).strip())

    elif input == 'bin':
        if file:
            with open(file, 'rb') as fd:
                buffer = fd.read()
        else:
            buffer = sys.stdin.buffer.read()

    if buffer is None:
        raise click.BadParameter('Problem load buffer.')

    if len(buffer) > 128:
        raise click.BadParameter('Buffer has wrong size allowed is max 128B')

    logger.debug('write uicr: %s', buffer.hex())

    prog = NRFJProg()
    prog.write_uicr(buffer)


def main():
    cli()
