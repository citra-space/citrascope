# CitraScope
[![Pytest](https://github.com/citra-space/citrascope/actions/workflows/pytest.yml/badge.svg)](https://github.com/citra-space/citrascope/actions/workflows/pytest.yml) [![Integration Tests](https://github.com/citra-space/citrascope/actions/workflows/integration-tests.yml/badge.svg)](https://github.com/citra-space/citrascope/actions/workflows/integration-tests.yml) [![Build and Push Docker Image](https://github.com/citra-space/citrascope/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/citra-space/citrascope/actions/workflows/docker-publish.yml) [![Publish Python 🐍 package](https://github.com/citra-space/citrascope/actions/workflows/publish.yml/badge.svg)](https://github.com/citra-space/citrascope/actions/workflows/publish.yml)source venv/bin/activate

Remotely control a telescope while it polls for tasks, collects observations, and delivers data for further processing.

## Features

- Connects to Citra.space's API and identifies itself as an online telescope
- Connects to configured INDI telescope and camera hardware
- Acts as a task daemon carrying out and remitting photography tasks

## Installation

Install CitraScope from PyPI:

```sh
pip install citrascope
```

### Optional Dependencies

CitraScope supports different hardware adapters through optional dependency groups:

- **INDI adapter** (for Linux-based telescope control):
  ```sh
  pip install citrascope[indi]
  ```

- **All optional dependencies**:
  ```sh
  pip install citrascope[all]
  ```

The base installation without optional dependencies supports the NINA adapter, which works via HTTP API calls and does not require additional Python packages.

This provides the `citrascope` command-line tool. To see available commands:

```sh
citrascope --help
```

## Usage

Run the CLI tool:

```sh
citrascope start
```

To connect to the Citra Dev server:

```sh
citrascope start --dev
```

## Configuration

Settings are managed via environment variables with the prefix `CITRASCOPE_`. You must configure your personal access token and telescope ID, as well as INDI server details. You can set these variables in your shell or in a `.env` file at the project root.

Example `.env` file:

```env
CITRASCOPE_PERSONAL_ACCESS_TOKEN=citra_pat_xxx
CITRASCOPE_TELESCOPE_ID=xxx
# CITRASCOPE_INDI_SERVER_URL=127.0.0.1
CITRASCOPE_INDI_SERVER_URL=host.docker.internal  # use with devcontainer for accessing a localhost indi server
CITRASCOPE_INDI_SERVER_PORT=7624
CITRASCOPE_INDI_TELESCOPE_NAME=Telescope Simulator
```

**Variable descriptions:**

- `CITRASCOPE_PERSONAL_ACCESS_TOKEN`: Your CitraScope personal access token (required)
- `CITRASCOPE_TELESCOPE_ID`: Your telescope ID (required)
- `CITRASCOPE_INDI_SERVER_URL`: Hostname or IP address of the INDI server (default: `host.docker.internal` for devcontainers, or `127.0.0.1` for local)
- `CITRASCOPE_INDI_SERVER_PORT`: Port for the INDI server (default: `7624`)
- `CITRASCOPE_INDI_TELESCOPE_NAME`: Name of the INDI telescope device (default: `Telescope Simulator`)

You can copy `.env.example` to `.env` and tweak your values.

## Developer Setup

If you are developing on macOS or Windows, use the provided [VS Code Dev Container](https://code.visualstudio.com/docs/devcontainers/containers) setup. The devcontainer provides a full Linux environment, which is required for the `pyindi-client` dependency to work. This is necessary because `pyindi-client` only works on Linux, and will not function natively on Mac or Windows.

By opening this project in VS Code and choosing "Reopen in Container" (or using the Dev Containers extension), you can develop and run the project seamlessly, regardless of your host OS.

The devcontainer also ensures all required system dependencies (like `cmake`) are installed automatically.

### Python Version

This project requires Python 3.9 or higher, up to Python 3.13. A `.python-version` file is included specifying Python 3.12 as the recommended version. If you use [pyenv](https://github.com/pyenv/pyenv), it will automatically use this version when you enter the project directory.

### If not using the dev container:
```sh
python -m venv .venv
source .venv/bin/activate
```

### Installing Development Dependencies

To install development dependencies (for code style, linting, and pre-commit hooks):

```sh
pip install '.[dev]'
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

### Running and Debugging with VS Code

If you are using Visual Studio Code, you can run or debug the project directly using the pre-configured launch options in `.vscode/launch.json`:

- **Python: citrascope dev start** — Runs the main entry point with development options.
- **Python: citrascope dev start DEBUG logging** — Runs with development options and sets log level to DEBUG for more detailed output.

To use these, open the Run and Debug panel in VS Code, select the desired configuration, and click the Run or Debug button. This is a convenient way to start or debug the app without manually entering commands.

## Running Tests

This project uses [pytest](https://pytest.org/) for unit testing. All tests are located in the `tests/` directory.

To run unit tests manually, within your devcontainer run:

```bash
pytest
```

The integration tests run in a dockerized context and as such can't run within the devcontainer. Instead, run this in your desktop's terminal:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit
```
