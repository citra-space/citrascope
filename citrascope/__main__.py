import click

from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.settings.citrascope_settings import CitraScopeSettings


@click.command()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.option("--keep-images", is_flag=True, default=False, help="Keep image files after upload (do not delete)")
@click.option("--web-port", default=24872, type=int, help="Web server port (default: 24872)")
def cli(dev, log_level, keep_images, web_port):
    settings = CitraScopeSettings(dev=dev, log_level=log_level, keep_images=keep_images, web_port=web_port)
    daemon = CitraScopeDaemon(settings)
    daemon.run()


if __name__ == "__main__":
    cli()
