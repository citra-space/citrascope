from dotenv import load_dotenv
load_dotenv()
import requests


import click
from citrascope.logging import CITRASCOPE_LOGGER
from citrascope.settings._citra_api_settings import CitraAPISettings






def check_api_key(settings):
    url = f"https://{settings.host}/auth/personal-access-tokens"
    headers = {"Authorization": f"Bearer {settings.personal_access_token}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        # CITRASCOPE_LOGGER.info(f"API key check response: {resp.status_code} {resp.text}")
        if resp.status_code == 200:
            CITRASCOPE_LOGGER.info("API key is valid. Connected to Citra API.")
            return True
        else:
            CITRASCOPE_LOGGER.error(f"API key check failed: {resp.status_code} {resp.text}")
            return False
    except Exception as e:
        CITRASCOPE_LOGGER.error(f"Error connecting to Citra API: {e}")
        return False

@click.group()
@click.option('--dev', is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.pass_context
def cli(ctx, dev):
    # Load settings and print them at startup
    settings = CitraAPISettings(dev=dev)
    check_api_key(settings)
    # Store settings in context for subcommands if needed
    ctx.obj = settings


@cli.group("start")
def start():
    CITRASCOPE_LOGGER.info(f"Starting remote telescope...")  # noqa


cli()
