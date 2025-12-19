# Copilot Instructions for CitraScope

## Overview
This project is a Python package for interacting with astronomical data and services. It includes modules for API clients, INDI client integration, logging, settings management, and task execution. Tests are located in the `tests/` directory.

## Coding Guidelines
- Follow PEP8 for Python code style.
- Use type hints for all public functions and methods.
- Write docstrings for all modules, classes, and functions.
- Prefer logging via the custom logger in `citrascope/logging/` over print statements.
- Organize code into logical modules as per the existing structure.

## Directory Structure
- `citrascope/api/`: API client code
- `citrascope/hardware/`: Hardware adapter implementations and registry
  - `adapter_registry.py`: Central registry for all hardware adapters (add new adapters here)
  - `abstract_astro_hardware_adapter.py`: Base class all adapters must implement
  - Individual adapter implementations (indi_adapter.py, nina_adv_http_adapter.py, etc.)
- `citrascope/logging/`: Logging utilities
- `citrascope/settings/`: Settings and configuration
- `citrascope/tasks/`: Task runner and definitions
- `citrascope/web/`: Web interface for monitoring and configuration
  - `citrascope/web/app.py`: FastAPI application and routes
  - `citrascope/web/server.py`: Web server management and threading
  - `citrascope/web/templates/`: HTML templates
  - `citrascope/web/static/`: CSS and JavaScript files
- `tests/`: Unit and integration tests

## Testing
- All new features and bug fixes should include corresponding tests in `tests/`.
- Use pytest for running tests.
- Test files should be named `test_*.py`.

## Copilot Usage
- When implementing new features, follow the module structure and add tests.
- For bug fixes, describe the issue and expected behavior in comments or commit messages.
- For refactoring, ensure no breaking changes and all tests pass.
- Use Copilot to suggest code, refactor, and generate tests, but always review suggestions for correctness and style.

## Common Tasks
- Add new API integrations in `citrascope/api/`.
- Extend or add hardware adapters:
  - Create new adapter class implementing `AbstractAstroHardwareAdapter` in `citrascope/hardware/`
  - Register it in `citrascope/hardware/adapter_registry.py` by adding an entry to `REGISTERED_ADAPTERS`
  - All adapter discovery and instantiation flows from this registry
- Update logging logic in `citrascope/logging/`.
- Change settings in `citrascope/settings/`.
- Add or modify tasks in `citrascope/tasks/`.
- Enhance web interface in `citrascope/web/`.
- Write or update tests in `tests/`.

## Web Interface Guidelines

The web interface provides real-time monitoring and configuration for telescope operations. When working on web-related features:

### Design Principles
- **Dark theme required**: All UI elements must use dark colors suitable for nighttime telescope operations to preserve night vision
- **Real-time updates**: Use WebSocket connections for live status, logs, and telemetry
- **Mobile-friendly**: The interface should be responsive and usable on tablets/phones in the field
- **Minimal distractions**: Reduce visual clutter; prioritize essential telescope and task information

### Architecture
- **FastAPI backend** (`web/app.py`): RESTful API endpoints and WebSocket handlers
- **Separate thread**: Web server runs in daemon thread with its own event loop (`web/server.py`)
- **Log streaming**: Custom `WebLogHandler` broadcasts logs to web clients in real-time
- **Static files**: HTML, CSS, and JavaScript are served from `web/templates/` and `web/static/`

### Development Notes
- Keep web-specific code isolated in the `citrascope/web/` directory
- The daemon should only call `web_server.start()` - all web complexity stays in `web/server.py`
- Filter out noise from web logs (HTTP requests, WebSocket events, Uvicorn messages)
- Use thread-safe mechanisms when accessing daemon state from web handlers
- Port 24872 (CITRA on phone keypad) is the default web interface port

## Important Packages

This project relies on several key Python packages. Below are some of the most important ones and their roles:

- **Click**: Used for building the command-line interface (CLI). The main entry point for the application (`python -m citrascope`) is implemented using Click.
- **Pydantic-Settings**: Manages configuration and settings, ensuring type safety and validation for environment variables.
- **Requests** and **HTTPX**: Handle HTTP requests for interacting with the Citra.space API.
- **Python-Dateutil**: Provides robust date and time parsing utilities.
- **PyINDI-Client**: Interfaces with INDI telescope hardware, enabling communication with telescope and camera devices.
- **Skyfield**: Used for astronomical calculations, such as determining celestial positions.
- **Pytest** and **Pytest-Cov**: Facilitate unit testing and code coverage analysis.

### Development Dependencies
- **Black**: Ensures consistent code formatting.
- **Pre-Commit**: Runs code quality checks automatically before commits.
- **Isort**: Sorts imports to maintain a clean and organized structure.
- **Mypy**: Performs static type checking.
- **Flake8**: Enforces code style and linting rules.
- **Sphinx**: Generates project documentation.

### Web Interface Dependencies
- **FastAPI**: Modern async web framework for the monitoring interface
- **Uvicorn**: ASGI server for running the web application
- **WebSockets**: Real-time bidirectional communication for live updates

For a complete list of dependencies, refer to the `pyproject.toml` file.

## Additional Notes
- Keep dependencies minimal and update `pyproject.toml` as needed.
- Documentation is maintained in the [citra-space/docs](https://github.com/citra-space/docs) repository under `docs/citrascope/`.
- Use pre-commit hooks for code quality.
