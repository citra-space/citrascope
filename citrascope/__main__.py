import click

from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.settings._citrascope_settings import CitraScopeSettings


@click.group()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.option("--keep-images", is_flag=True, default=False, help="Keep image files after upload (do not delete)")
@click.pass_context
def cli(ctx, dev, log_level, keep_images):
    ctx.obj = {"settings": CitraScopeSettings(dev=dev, log_level=log_level, keep_images=keep_images)}


@cli.command("start")
@click.pass_context
def start(ctx):
    daemon = CitraScopeDaemon(ctx.obj["settings"])
    daemon.run()


if __name__ == "__main__":
    cli()
