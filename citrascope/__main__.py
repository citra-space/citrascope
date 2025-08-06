import click
from citrascope.logging import CITRASCOPE_LOGGER


@click.group()
def cli():
    pass


@cli.group("start")
def start():
    CITRASCOPE_LOGGER.info(f"Starting remote telescope...")  # noqa


cli()
