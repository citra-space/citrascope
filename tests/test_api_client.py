import pytest

from citrascope.api.client import CitraApiClient

from .utils import DummyLogger


# Test CitraApiClient basic instantiation
@pytest.mark.parametrize("host,token", [("localhost", "dummy-token")])
def test_api_client_init(host, token):
    client = CitraApiClient(host, token, use_ssl=False, logger=DummyLogger())
    assert client.base_url == f"http://{host}"
    assert client.token == token
    assert hasattr(client, "client")


# Test check_api_key returns False on connection error
@pytest.mark.usefixtures("monkeypatch")
def test_check_api_key_error(monkeypatch):
    class DummyClient:
        def get(self, url):
            raise Exception("Connection error")

    logger = DummyLogger()
    client = CitraApiClient("localhost", "token", use_ssl=False, logger=logger)
    client.client = DummyClient()
    result = client.check_api_key()
    assert result is False
    assert any("Error connecting" in msg for msg in logger.errors)
