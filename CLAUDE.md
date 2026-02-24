# CLAUDE.md — Agent Guide for CitraScope

## What is this project?

CitraScope is a Python daemon that runs at a telescope. It polls a backend API for observation tasks, controls hardware (mount, camera, filter wheel, focuser) to capture images, runs an edge-processing pipeline (plate solving, source extraction, photometry, satellite matching), and uploads results. It also serves a local web UI for operators to monitor and configure the system.

**Backend API**: https://dev.api.citra.space/docs (Swagger)

## Quick start

```bash
pip install -e ".[dev,test]"
pytest -m "not integration"
python -m citrascope  # starts the daemon
```

Web UI runs on port **24872** (CITRA on a phone keypad).

Config lives at `~/Library/Application Support/citrascope/config.json` (macOS) or platform equivalent via `platformdirs`.

## Architecture overview

```
__main__.py (CLI via Click)
  └─ citra_scope_daemon.py (lifecycle, main loop)
       ├─ api/ (CitraApiClient, DummyApiClient for local testing)
       ├─ hardware/ (adapter pattern — abstract base + concrete implementations)
       │    ├─ abstract_astro_hardware_adapter.py (the contract)
       │    ├─ adapter_registry.py (add new adapters here)
       │    ├─ filter_sync.py, dummy_adapter.py (shared utilities)
       │    ├─ nina/ (adapter, event_listener, survey_template)
       │    ├─ kstars/ (adapter, scheduler_template, sequence_template)
       │    ├─ indi/ (adapter)
       │    ├─ direct/ (adapter)
       │    └─ devices/ (direct USB/RPi/Ximea cameras)
       ├─ tasks/
       │    ├─ runner.py (TaskManager — orchestrates the main loop)
       │    ├─ autofocus_manager.py (dedicated autofocus scheduling/execution)
       │    ├─ base_work_queue.py → imaging_queue.py, processing_queue.py, upload_queue.py
       │    └─ scope/ (base_telescope_task.py, static/tracking variants)
       ├─ processors/ (pluggable pipeline: plate_solver → source_extractor → photometry → satellite_matcher)
       ├─ settings/ (CitraScopeSettings, persisted to JSON)
       └─ web/ (FastAPI app, Alpine.js frontend, WebSocket log streaming)
```

## Critical conventions

### RA/Dec are always in degrees internally

Every function, API call, and data structure uses **degrees** for both RA and Dec. Conversions to/from hours happen only at hardware boundaries:
- **INDI**: expects RA in hours → convert `ra / 15.0` before sending, `ra * 15.0` when reading
- **KStars D-Bus**: same as INDI
- **NINA Advanced API**: accepts degrees natively, no conversion needed
- **Citra API**: degrees
- **FITS WCS, Astropy, Skyfield**: degrees

If you touch any coordinate code, verify the units. This has been a source of real bugs.

### Hardware adapters

All adapters implement `AbstractAstroHardwareAdapter`. Key methods:
- `connect()` / `disconnect()`
- `do_autofocus(target_ra, target_dec, on_progress)` — all in degrees
- `perform_observation_sequence(task, satellite_data)` — returns file paths
- `point_telescope(ra, dec)` — degrees

To add a new adapter: create the class in `citrascope/hardware/`, register it in `adapter_registry.py`.

The NINA adapter uses a **WebSocket event listener** (`nina/event_listener.py`) for reactive hardware control instead of polling. The pattern is: `event.clear()` → issue command via REST → `event.wait(timeout=...)`. Key events: `SEQUENCE-FINISHED`, `IMAGE-SAVE`, `FILTERWHEEL-CHANGED`, `AUTOFOCUS-FINISHED`.

### Work queues

Tasks flow through three serial queues: **ImagingQueue** → **ProcessingQueue** → **UploadQueue**. Each has background worker threads. Use `queue.is_idle()` to check if a queue has pending work.

### Web UI

- **Dark theme required** — operators use this at night, preserve night vision
- **Mobile-friendly** — the UI is used on tablets/phones in the field
- **FastAPI** backend in `web/app.py`, **Alpine.js** frontend in `web/static/`
- Real-time updates via WebSocket at `/ws` (`WebLogHandler` broadcasts logs to connected clients)
- Templates in `web/templates/` (Jinja2 partials prefixed with `_`)
- The web server runs in a **daemon thread** with its own event loop (`web/server.py`). Use thread-safe mechanisms when accessing daemon state from web handlers. The daemon only calls `web_server.start()` — all web complexity stays in `web/server.py`.

### Adding a new setting (full checklist)

**Agents frequently miss steps here.** A setting must be wired in **four** places or it silently fails to save or load:

1. **`settings/citrascope_settings.py` — `__init__`**: Load from config dict with a default:
   ```python
   self.my_setting: str = config.get("my_setting", "default_value")
   ```

2. **`settings/citrascope_settings.py` — `to_dict()`**: Add to the returned dict so it gets persisted:
   ```python
   "my_setting": self.my_setting,
   ```
   *If you skip this, the setting loads from the file but is never written back — it vanishes on next save.*

3. **`web/app.py` — `GET /api/config` response**: Add to the response dict in `get_config()` so the UI can read it:
   ```python
   "my_setting": settings.my_setting,
   ```
   *If you skip this, the setting exists server-side but the web UI never sees it.*

4. **`web/static/config.js` — `saveConfiguration()`**: Add to the `config` object so the UI sends it back on save:
   ```javascript
   my_setting: formConfig.my_setting || 'default_value',
   ```
   *If you skip this, the UI reads the setting fine but drops it when the user saves config.*

5. **(If UI-editable)** Add the input/control to the relevant HTML template in `web/templates/`.

The `GET /api/config` response and `to_dict()` look nearly identical but are **separate code paths** — the API response includes extra computed fields (`app_url`, `config_file_path`, etc.) that aren't in `to_dict()`. Both must include the setting.

For validation, add it in `__init__` after loading (see autofocus RA/Dec validation for the pattern).

### Adapter settings persistence

`_all_adapter_settings` in `CitraScopeSettings` is a nested dict keyed by adapter name (e.g., `"NinaAdvancedHttpAdapter"`). Each entry contains adapter-specific settings *including* a `"filters"` key saved by `_save_filter_config()`. The web form sends flat adapter_settings for only the **current** adapter — `update_and_save()` must **merge** incoming settings with existing ones, not replace the entire dict. Replacing it will silently wipe filters and other adapter-specific state.

### Task lifecycle and race conditions

After imaging completes, a task is in-flight through processing and upload queues. The next poll cycle can see it's not the `current_task_id` and not yet removed from the API response — re-adding it causes duplicate imaging and 404 errors on the second upload attempt. The `_stage_lock` vs `heap_lock` ordering matters: `remove_task_from_all_stages` acquires `_stage_lock` then `heap_lock`, so any code that needs both must follow the same order to avoid deadlocks.

## Coding standards

- **Python 3.10+**, line length **120** (Black)
- **Type hints** on public methods. Use `Type | None` for nullable attrs.
- Use `from __future__ import annotations` + `if TYPE_CHECKING:` to avoid circular imports with type hints.
- Use `assert self.thing is not None` to satisfy type checkers when an attribute is guaranteed set after `connect()`.
- **Logging**: use the project logger (`self.logger`), never `print()`.
- **Tests**: `pytest`, files named `test_*.py` in `tests/unit/` or `tests/integration/`. Mark integration tests with `@pytest.mark.integration`.
- Run tests: `pytest -m "not integration"`

## Common pitfalls

- **DummyApiClient** returns snake_case keys (matching the real Citra API), not camelCase. The NINA API uses camelCase — don't confuse the two.
- **Task.from_dict** parses camelCase keys from the Citra API (e.g., `assignedFilterName`).
- **NINA WebSocket event ordering**: `SEQUENCE-FINISHED` arrives before `IMAGE-SAVE`. Don't query image history until IMAGE-SAVE confirms the file is written.
- **NINA's IMAGE-SAVE payload** does not include an `Index` field despite what the wiki says. Match by `Filename`, then look up the index via `/image-history`.
- **Focuser move** has no WebSocket event — still requires polling.
- **AutofocusManager** gates on `imaging_queue.is_idle()` to prevent hardware collisions with active imaging tasks.
- **`formatLastAutofocus`** (JS) has a sanity check for timestamps before 2020-01-01 — returns "Never" for obviously wrong values.
- **NINA WebSocket is always available** if the REST API is. There's no configuration to disable it separately. Don't add HTTP polling fallbacks — they add complexity for a case that can't happen.
- **NINA autofocus can infinite-loop** without a timeout. Always use a timeout (currently 300s) when waiting for results from `/focuser/last-af`.
- **Alpine.js `x-show` vs HTML5 `required`**: `x-show` keeps hidden elements in the DOM, but `required` attributes still fire validation on them. Use `:required="visible"` or `x-if`.
- **Alpine store load ordering**: If a `<select>` depends on API-fetched options (e.g., autofocus presets), fetch those *before* setting the config that references them, or the UI renders with stale/empty options.
- **After renaming a parameter**, search the entire method/file for the old name. Long methods have had stale references survive "first pass" refactors, causing `NameError`s at runtime.
- **Don't invent redundant settings.** Before adding one, check if an existing setting already controls the same behavior.
- **Pre-commit hooks**: The repo has a 500KB file size limit. FITS files and large binaries will be rejected.

## Key dependencies

- **Click**: CLI entry point (`python -m citrascope`)
- **FastAPI** + **Uvicorn**: Web UI and API, runs in a daemon thread
- **Requests**: HTTP calls to Citra API and NINA REST API
- **websockets**: NINA WebSocket event listener
- **Skyfield**: Astronomical calculations (celestial positions, satellite passes)
- **Astropy**: FITS file I/O, WCS, coordinate transforms
- **Alpine.js**: Reactive frontend (loaded via CDN, no build step)

Dev tools: **Black** (formatter), **isort** (imports), **mypy** (type checking), **pytest** + **pytest-cov** (testing). Pre-commit hooks run these automatically.

Full dependency list in `pyproject.toml`.

## External APIs

- **Citra API**: `https://dev.api.citra.space/docs` — task polling, filter sync, observation upload
- **NINA Advanced API**: REST at `http://<host>:1888/v2/api`, WebSocket at `ws://<host>:1888/v2/socket` — [docs](https://github.com/christian-photo/ninaAPI/wiki/Websocket-V2)
- **INDI**: XML protocol over TCP, via `pyindi-client`
- **KStars**: D-Bus interface, requires `dbus-python`

## Documentation

Project documentation is maintained in the [citra-space/docs](https://github.com/citra-space/docs) repository under `docs/citrascope/`.
