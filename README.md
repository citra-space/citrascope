
# Remote Telescope

Remotely control a telescope while it polls for tasks, collects observations, and delivers data for further processing.


## Installation


Before running the project, install the required dependencies. It is recommended to use a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install .

# To install development dependencies (for code style, linting, and pre-commit hooks), run:

```sh
pip install '.[dev]'
```
```

### Setting up Pre-commit Hooks

This project uses [pre-commit](https://pre-commit.com/) to run code quality checks (like Flake8, Black, isort, etc.) automatically before each commit.

After installing the dev dependencies, enable the hooks with:

```sh
pre-commit install
```

You can manually run all pre-commit checks on all files with:

```sh
pre-commit run --all-files
```

This ensures code style and quality checks are enforced for all contributors.

## Running the Project

This project uses a command-line interface (CLI) built with [Click](https://click.palletsprojects.com/). To run the CLI:

```sh
python -m citrascope start
```

When the app starts, it will load and display the current settings.

### Configuring Settings


Settings are managed via environment variables with the prefix `CITRA_API_`. You must configure your personal access token and telescope ID. For example:

```sh
export CITRA_API_PERSONAL_ACCESS_TOKEN="your-token"
export CITRA_API_TELESCOPE_ID="your-telescope-id"
```

These are also available for overriding via your .env file:

```sh
export CITRA_API_HOST="your-api-host"
export CITRA_API_PORT=1234
export CITRA_API_USE_SSL=true
```

You can set these variables in your shell or in a `.env` file.
