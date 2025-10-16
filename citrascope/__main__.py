import time

import click
from dotenv import load_dotenv

from citrascope.api.client import CitraApiClient
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citra_api_settings import CitraAPISettings
from citrascope.tasks.runner import TaskManager

load_dotenv()


@click.group()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.pass_context
def cli(ctx, dev, log_level):
    CITRASCOPE_LOGGER.setLevel(log_level)
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
    settings = ctx.obj["settings"]
    if not client.check_api_key():
        CITRASCOPE_LOGGER.error("Aborting: could not authenticate with Citra API.")
        return
    if not client.check_telescope_id(settings.telescope_id):
        CITRASCOPE_LOGGER.error("Aborting: telescope_id is not valid on the server.")
        return

    task_manager = TaskManager(client, settings.telescope_id, CITRASCOPE_LOGGER)
    task_manager.start()

    CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        CITRASCOPE_LOGGER.info("Shutting down daemon.")
        task_manager.stop()


cli()
