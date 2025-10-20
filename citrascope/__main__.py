import sys
import time

import click
from dotenv import load_dotenv

from citrascope.api.client import CitraApiClient
from citrascope.indi.CitraIndiClient import CitraIndiClient
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citrascope_settings import CitraScopeSettings
from citrascope.tasks.runner import TaskManager

load_dotenv()


@click.group()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.pass_context
def cli(ctx, dev, log_level):
    CITRASCOPE_LOGGER.setLevel(log_level)
    # Load settings and print them at startup
    settings = CitraScopeSettings(dev=dev)
    CITRASCOPE_LOGGER.info(f"CitraAPISettings host is {settings.host}")
    CITRASCOPE_LOGGER.info(f"CitraAPISettings telescope_id is {settings.telescope_id}")
    api_client = CitraApiClient(settings.host, settings.personal_access_token, settings.use_ssl, CITRASCOPE_LOGGER)
    # Store both settings and api_client in context for subcommands
    ctx.obj = {"settings": settings, "api_client": api_client}


@cli.command("start")
@click.pass_context
def start(ctx):
    api_client: CitraApiClient = ctx.obj["api_client"]
    settings = ctx.obj["settings"]
    if not api_client.check_api_key():
        CITRASCOPE_LOGGER.error("Aborting: could not authenticate with Citra API.")
        return

    # get telescope from api
    citra_telescope_record = api_client.check_telescope_id(settings.telescope_id)
    ctx.citra_telescope_record = citra_telescope_record
    if not citra_telescope_record:
        CITRASCOPE_LOGGER.error("Aborting: telescope_id is not valid on the server.")
        return

    # get ground station from api
    ground_station = api_client.get_ground_station(citra_telescope_record["groundStationId"])
    if not ground_station:
        CITRASCOPE_LOGGER.error("Aborting: could not get ground station info from the server.")
        return

    # INDI server connection
    CITRASCOPE_LOGGER.info(f"Connecting to INDI server at {settings.indi_server_url}: {settings.indi_server_port}")
    indi_client = CitraIndiClient(CITRASCOPE_LOGGER)
    indi_client.setServer(settings.indi_server_url, int(settings.indi_server_port))
    print("Connecting and waiting 1 sec")
    if not indi_client.connectServer():
        print(f"No INDI server running on {indi_client.getHost()}:{indi_client.getPort()}")
        return

    # Waiting for discover devices
    time.sleep(1)

    CITRASCOPE_LOGGER.info("List of INDI devices")
    deviceList = indi_client.getDevices()
    for device in deviceList:
        CITRASCOPE_LOGGER.info(f"   > {device.getDeviceName()}")
        if device.getDeviceName() == settings.indi_telescope_name:
            indi_client.our_scope = device
            CITRASCOPE_LOGGER.info("Found configured Telescope on INDI server!")

    task_manager = TaskManager(api_client, citra_telescope_record, ground_station, CITRASCOPE_LOGGER, indi_client)
    task_manager.start()

    CITRASCOPE_LOGGER.info("Starting telescope task daemon... (press Ctrl+C to exit)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        CITRASCOPE_LOGGER.info("Shutting down daemon.")
        task_manager.stop()


cli()
