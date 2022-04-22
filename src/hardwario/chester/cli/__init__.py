import click
from . import app, lte


@click.group(name='chester', help='Commands for CHESTER (configurable IoT gateway).')
@click.pass_context
def cli(ctx):
    pass


cli.add_command(app.cli)
cli.add_command(lte.cli)


def main():
    cli(obj={})
