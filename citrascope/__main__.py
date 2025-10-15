

import click
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citra_api_settings import CitraAPISettings





@click.group()
@click.option('--dev', is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.pass_context
def cli(ctx, dev):
    # Load settings and print them at startup
    settings = CitraAPISettings(dev=dev)
    CITRASCOPE_LOGGER.info("Loaded settings at startup:")
    for field, value in settings.model_dump().items():
        CITRASCOPE_LOGGER.info(f"  {field}: {value}")
    # Store settings in context for subcommands if needed
    ctx.obj = settings


@cli.group("start")
def start():
    CITRASCOPE_LOGGER.info(f"Starting remote telescope...")  # noqa


cli()
