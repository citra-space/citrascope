import click

from citrascope.citra_scope_daemon import CitraScopeDaemon
from citrascope.constants import DEFAULT_WEB_PORT
from citrascope.settings.citrascope_settings import CitraScopeSettings
from citrascope.version import format_version_cli, get_version_info


def _version_string() -> str:
    return format_version_cli(get_version_info())


@click.command()
@click.version_option(version=_version_string(), prog_name="citrascope")
@click.option(
    "--web-port",
    default=DEFAULT_WEB_PORT,
    type=int,
    help=f"Web server port (default: {DEFAULT_WEB_PORT})",
)
def cli(web_port):
    """CitraScope daemon - configure via web UI at http://localhost:24872"""
    settings = CitraScopeSettings.load(web_port=web_port)
    daemon = CitraScopeDaemon(settings)
    daemon.run()


if __name__ == "__main__":
    cli()
