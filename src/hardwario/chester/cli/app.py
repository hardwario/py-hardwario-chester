import logging
import re
import click
import sys
from ..pib import PIB, hw_variant_to_number
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


def validate_serial_number(ctx, param, value):
    if not value:
        return value

    if isinstance(value, int):
        if (value & 0xc0000000) != 0x80000000:
            raise click.BadParameter('Bad serial number format')
        return value

    return int(value)


def validate_hw_revision(ctx, param, value):
    if isinstance(value, int):
        return value

    if value.startswith('0x'):
        return int(value[2:], 16)

    m = re.match(r'^R(\d+)\.(\d+)$', str(value))
    if not m:
        raise click.BadParameter('Bad Hardware version format, try again')
    major, minor = m.groups()
    return (int(major) << 8) | int(minor)


hw_variant_list = [
    'CHESTER-M-BCDGLS',
    'CHESTER-M-BCGLS',
    'CHESTER-M-BCGS',
    'CHESTER-M-BCGV',
    'CHESTER-M-BCS',
    'CHESTER-M-BCV',
    'CHESTER-M-BL',
    'CHESTER-M-CGLS',
    'CHESTER-M-CGS',
    'CHESTER-M-CGV',
    'CHESTER-M-CS',
    'CHESTER-M-CV',
    'CHESTER-M-L'
]


def validate_hw_variant(ctx, param, value):
    if isinstance(value, int):
        if (value < 0) or (value > 2**32):
            raise click.BadParameter('Bad Hardware variant format')
        return value

    if isinstance(value, str):
        if value == '':
            return 0
        if value not in hw_variant_list:
            raise click.BadParameter('Bad Hardware variant not from options')

        return hw_variant_to_number(value)

    if value.startswith('0x'):
        return int(value[2:], 16)
    return int(value)


def validate_ble_passkey(ctx, param, value):
    if len(value) > 15:
        raise click.BadParameter('Tool long BLE passkey, max 15 characters.')
    return value


@cli.group(name='uicr')
def group_uicr():
    '''UICR flash area.'''
    pass


@group_uicr.command('read')
@click.option('--pib', 'output', flag_value='pib', required=True, help='Read HARDWARIO Product Information Block from UICR.')
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
        print(f'Serial number: {pib.get_serial_number()}')
        print(f'Vendor name: {pib.get_vendor_name()}')
        print(f'Product name: {pib.get_product_name()}')
        print(f'Hardware revision: 0x{pib.get_hw_revision():04x}')
        print(f'Hardware variant: 0x{pib.get_hw_variant():08x}')
        print(f'BLE passkey: {pib.get_ble_passkey()}')

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


@ group_uicr.command('write')
@click.option('--pib', 'input', flag_value='pib', required=True, help='Write HARDWARIO Product Information Block to UICR.')
@click.option('--bin', 'input', flag_value='bin', required=True, help='Write generic UICR flash area from <FILE> or stdin.')
@click.option('--hex', 'input', flag_value='hex', required=True, help='Write generic UICR flash area from <FILE> or stdin.')
@ click.option('--vendor-name', type=str, help='Vendor name (max 31 characters).', default='HARDWARIO', prompt='--pib' in sys.argv, show_default=True)
@ click.option('--product-name', type=str, help='Product name (max 31 characters).', default='CHESTER-M', prompt='--pib' in sys.argv, show_default=True)
@ click.option('--hw-revision', type=click.UNPROCESSED, help='Hardware revision in Rx.y format.', default='R3.2', prompt='Hardware revision' if '--pib' in sys.argv else False, show_default=True, callback=validate_hw_revision)
@ click.option('--hw-variant', type=click.UNPROCESSED, help=hw_variant_help, default='', prompt='Hardware variant' if '--pib' in sys.argv else False, show_default=True, callback=validate_hw_variant)
@ click.option('--serial-number', type=click.UNPROCESSED, help='Serial number in decimal format.', prompt='--pib' in sys.argv, callback=validate_serial_number)
@ click.option('--ble-passkey', type=str, help='Bluetooth security passkey.', default='123456', prompt='--pib' in sys.argv, show_default=True, callback=validate_ble_passkey)
@ click.argument('file', metavar="<FILE>", nargs=-1)
def command_uicr_write(input, serial_number, vendor_name, product_name, hw_revision, hw_variant, ble_passkey, file):
    logger.debug("command_pib_write: %s", (input, serial_number,
                 vendor_name, product_name, hw_revision, hw_variant, ble_passkey, file))
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
