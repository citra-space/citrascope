
# Remote Telescope

Remotely control a telescope while it polls for tasks, collects observations, and delivers data for further processing.


## Installation


Before running the project, install the required dependencies. It is recommended to use a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

## Running the Project

This project uses a command-line interface (CLI) built with [Click](https://click.palletsprojects.com/). To run the CLI:

```sh
python -m citrascope start
```

When the app starts, it will load and display the current settings.

### Configuring Settings

Settings are managed via environment variables with the prefix `CITRA_API_`. You must configure your personal access token. For example:

```sh
export CITRA_API_PERSONAL_ACCESS_TOKEN="your-token"
```

These are also available for overriding via your .env file:

```sh
export CITRA_API_HOST="your-api-host"
export CITRA_API_PORT=1234
export CITRA_API_USE_SSL=true
```

You can set these variables in your shell or in a `.env` file.
