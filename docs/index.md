# CitraScope Documentation

Welcome to the CitraScope documentation.

## Overview

CitraScope is a Python application for remote telescope control, task automation, and data collection.
It connects to the Citra.space API and INDI hardware to execute observation tasks.

## Architecture

- **CLI Entrypoint:** `citrascope/__main__.py`
  Handles configuration, authentication, and starts the task daemon.
- **API Client:** `citrascope/api/client.py`
  Communicates with Citra.space for authentication, telescope, satellite, and ground station data.
- **Task Management:** `citrascope/tasks/runner.py`
  Polls for tasks, schedules, and executes observations.
- **Settings:** `citrascope/settings/_citrascope_settings.py`
  Loads configuration from environment variables.

## Configuration

See [README.md](../README.md) for installation and environment setup.
Environment variables are documented in `.env.example`.

## Usage

Run the CLI:
```sh
python -m citrascope
```
Or use VS Code launch configurations for development and debugging.

## Testing

- **Unit tests** are written using [pytest](https://pytest.org/) and are located in the `tests/` directory.
- To run tests manually, use:

  ```bash
  pytest
  ```

## Further Documentation

- [API Reference](https://api.citra.space/docs)
- [Contributing Guide](contributing.md) (coming soon)
- [Troubleshooting](troubleshooting.md) (coming soon)
