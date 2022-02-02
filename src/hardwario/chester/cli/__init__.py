import logging
import click
from . import app

logger = logging.getLogger(__name__)


@click.group(name='chester', help='CHESTER tools')
@click.pass_context
def cli(ctx):
    pass


cli.add_command(app.cli)
