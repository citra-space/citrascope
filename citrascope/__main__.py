from dotenv import load_dotenv
load_dotenv()
from citrascope.api.client import CitraApiClient


import click
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citra_api_settings import CitraAPISettings




@click.group()
@click.option('--dev', is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.pass_context

def cli(ctx, dev):
    # Load settings and print them at startup
    settings = CitraAPISettings(dev=dev)
    CITRASCOPE_LOGGER.info(f"CitraAPISettings host is {settings.host}")
    CITRASCOPE_LOGGER.info(f"CitraAPISettings telescope_id is {settings.telescope_id}")
    client = CitraApiClient(settings.host, settings.personal_access_token, settings.use_ssl, CITRASCOPE_LOGGER)
    # Store both settings and client in context for subcommands
    ctx.obj = {"settings": settings, "client": client}




@cli.command("start")
@click.pass_context
def start(ctx):
    client = ctx.obj["client"]
    if not client.check_api_key():
        CITRASCOPE_LOGGER.error("Aborting: could not authenticate with Citra API.")
        return
    CITRASCOPE_LOGGER.info("Starting remote telescope...")


cli()
