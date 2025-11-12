import os
import subprocess
import time

import pytest
import requests


@pytest.fixture(scope="session", autouse=True)
def docker_services():
    """Start docker-compose before integration tests and tear down after."""
    # Skip fixture if running inside Docker (docker-compose handles services)
    if os.environ.get("CITRASCOPE_API_URL"):
        print("\n✅ Running inside Docker - services managed by docker-compose")
        yield
        return

    # Fix the path - __file__ is already in tests/integration/, so just use the filename
    compose_file = os.path.join(os.path.dirname(__file__), "docker-compose.test.yml")

    # Try to detect docker compose command (v2 uses 'docker compose', v1 uses 'docker-compose')
    docker_cmd = None
    try:
        subprocess.run(["docker", "compose", "version"], check=True, capture_output=True)
        docker_cmd = ["docker", "compose"]
    except (FileNotFoundError, subprocess.CalledProcessError):
        try:
            subprocess.run(["docker-compose", "--version"], check=True, capture_output=True)
            docker_cmd = ["docker-compose"]
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    if docker_cmd is None:
        pytest.skip("Docker or Docker Compose not available - skipping integration tests that require Docker services")

    # Start services
    print("\n🚀 Starting Docker Compose services for integration tests...")
    subprocess.run(docker_cmd + ["-f", compose_file, "up", "-d", "indi", "mock-citra-server"], check=True)

    # Wait for services to be ready
    print("⏳ Waiting for services to be ready...")
    time.sleep(5)

    # Wait for mock server to be healthy
    for i in range(30):
        try:
            response = requests.get("http://localhost:8080/health", timeout=1)
            if response.status_code == 200:
                print("✅ Mock Citra server is ready")
                break
        except (requests.ConnectionError, requests.Timeout):
            time.sleep(1)
    else:
        print("⚠️  Warning: Mock server may not be ready")

    yield

    # Tear down
    print("\n🧹 Tearing down Docker Compose services...")
    subprocess.run(docker_cmd + ["-f", compose_file, "down", "-v"], check=True)
