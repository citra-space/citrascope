import pytest

from citrascope.indi.CitraIndiClient import CitraIndiClient

from .utils import DummyLogger


class DummyDevice:
    def getDeviceName(self):
        return "TestScope"


class DummyProperty:
    def getName(self):
        return "TestProp"

    def getTypeAsString(self):
        return "INDI_TEXT"

    def getDeviceName(self):
        return "TestScope"


@pytest.mark.usefixtures("monkeypatch")
def test_new_device_logs(monkeypatch):
    logger = DummyLogger()
    client = CitraIndiClient(logger)
    device = DummyDevice()
    client.newDevice(device)
    assert any("new device" in msg for msg in logger.infos)


@pytest.mark.usefixtures("monkeypatch")
def test_new_property_logs(monkeypatch):
    logger = DummyLogger()
    client = CitraIndiClient(logger)
    prop = DummyProperty()
    client.newProperty(prop)
    assert any("new property" in msg for msg in logger.debugs)
