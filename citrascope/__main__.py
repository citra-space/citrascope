import click

from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.settings._citrascope_settings import CitraScopeSettings


@click.group()
@click.option("--dev", is_flag=True, default=False, help="Use the development API (dev.app.citra.space)")
@click.option("--log-level", default="INFO", help="Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")
@click.option("--keep-images", is_flag=True, default=False, help="Keep image files after upload (do not delete)")
@click.option("--bypass-autofocus", is_flag=True, default=False, help="Skip autofocus routine when selecting telescope")
@click.pass_context
def cli(ctx, dev, log_level, keep_images, bypass_autofocus):
    ctx.obj = {
        "settings": CitraScopeSettings(
            dev=dev, log_level=log_level, keep_images=keep_images, bypass_autofocus=bypass_autofocus
        )
    }


@cli.command("start")
@click.option("--web-host", default="0.0.0.0", help="Web server host address (default: 0.0.0.0)")
@click.option("--web-port", default=24872, type=int, help="Web server port (default: 24872)")
@click.pass_context
def start(ctx, web_host, web_port):
    daemon = CitraScopeDaemon(ctx.obj["settings"], enable_web=True, web_host=web_host, web_port=web_port)
    daemon.run()


if __name__ == "__main__":
    cli()
