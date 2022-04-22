import click
import tempfile
import zipfile
import os
from loguru import logger
from ..pib import PIB, PIBException
from ..nrfjprog import NRFJProg


@click.group(name='lte')
@click.option('--nrfjprog-log', is_flag=True, help='Enable NRFJProg log.')
@click.pass_context
def cli(ctx, nrfjprog_log):
    '''LTE Modem SoC commands.'''
    ctx.obj['prog'] = NRFJProg('lte', log=nrfjprog_log)


@cli.command('flash')
@click.argument('file', metavar='FILE', type=click.Path(exists=True))
@click.pass_context
def command_flash(ctx, file):
    '''Flash modem firmware.'''

    def progress(text, ctx={'len': 0}):
        if ctx['len']:
            click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
        if not text:
            return
        text = f'  {text}'
        ctx['len'] = len(text)
        click.echo(text, nl=text == 'Successfully completed')

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
@click.pass_context
def command_erase(ctx):
    '''Erase modem firmware.'''
    with ctx.obj['prog'] as prog:
        prog.erase_all()


@ cli.command('reset')
@ click.pass_context
def command_reset(ctx):
    '''Reset modem firmware.'''
    with ctx.obj['prog'] as prog:
        prog.reset()


def main():
    cli()
