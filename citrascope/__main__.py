import click

from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.settings._citrascope_settings import CitraScopeSettings


@click.group()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.pass_context
def cli(ctx, dev, log_level):
    ctx.obj = {"dev": dev, "log_level": log_level}


@cli.command("start")
@click.pass_context
def start(ctx):
    settings = CitraScopeSettings(dev=ctx.obj["dev"], log_level=ctx.obj["log_level"])
    daemon = CitraScopeDaemon(settings)
    daemon.run()


if __name__ == "__main__":
    cli()
