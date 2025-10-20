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
- `citrascope/indi/`: INDI client integration
- `citrascope/logging/`: Logging utilities
- `citrascope/settings/`: Settings and configuration
- `citrascope/tasks/`: Task runner and definitions
- `tests/`: Unit and integration tests
- `docs/`: Project documentation

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
- Extend INDI client features in `citrascope/indi/`.
- Update logging logic in `citrascope/logging/`.
- Change settings in `citrascope/settings/`.
- Add or modify tasks in `citrascope/tasks/`.
- Write or update tests in `tests/`.

## Important Packages

This project relies on several key Python packages. Below are some of the most important ones and their roles:

- **Click**: Used for building the command-line interface (CLI). The main entry point for the application (`python -m citrascope start`) is implemented using Click.
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

For a complete list of dependencies, refer to the `pyproject.toml` file.

## Additional Notes
- Keep dependencies minimal and update `pyproject.toml` as needed.
- Document any major changes in `docs/index.md`.
- Use pre-commit hooks for code quality.
