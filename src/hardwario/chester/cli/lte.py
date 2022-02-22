import logging
from tkinter.messagebox import NO
import click
import tempfile
import zipfile
import re
import os
from ..pib import PIB, PIBException
from ..nrfjprog import NRFJProg


logger = logging.getLogger(__name__)


@click.group(name='lte')
@click.option('--nrfjprog-log', is_flag=True, help="Enable NRFJProg log.")
@click.pass_context
def cli(ctx, nrfjprog_log):
    '''LTE Modem SoC commands.'''
    ctx.obj['prog'] = NRFJProg('lte', log=nrfjprog_log)


@cli.command('flash')
@click.argument('file', metavar="FILE")
@click.pass_context
def command_flash(ctx, file):
    '''Flash modem firmware.'''

    if file.endswith('.zip'):
        zf = zipfile.ZipFile(file)
        namelist = zf.namelist()
        if len(namelist) == 2:
            if not 'modem.zip' in namelist or not 'application.hex' in namelist:
                raise Exception('Invalid file.')

            with tempfile.TemporaryDirectory() as temp_dir:
                zf.extractall(temp_dir)
                prog = ctx.obj['prog']
                prog.open()
                click.echo(f'Flash: modem.zip')
                prog.program(os.path.join(temp_dir, 'modem.zip'))
                click.echo(f'Flash: application.hex')
                prog.program(os.path.join(temp_dir, 'application.hex'))
                return

    prog = ctx.obj['prog']
    prog.open()
    click.echo(f'Flash: {file}')
    prog.program(file)


@cli.command('erase')
@click.pass_context
def command_erase(ctx):
    '''Erase modem firmware.'''
    prog = ctx.obj['prog']
    prog.open()
    prog.erase_all()


@ cli.command('reset')
@ click.pass_context
def command_reset(ctx):
    '''Reset modem firmware.'''
    prog = ctx.obj['prog']
    prog.open()
    prog.reset()


def main():
    cli()
