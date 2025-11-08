import pytest

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


# Synthetic adapter for testing
class TestHardwareAdapter:
    def __init__(self, logger, host, port):
        self.logger = logger
        self.host = host
        self.port = port

    def newDevice(self, device):
        self.logger.infos.append(f"new device: {device.getDeviceName()}")

    def newProperty(self, prop):
        self.logger.debugs.append(
            f"new property: {prop.getName()} ({prop.getTypeAsString()}) on {prop.getDeviceName()}"
        )


@pytest.mark.usefixtures("monkeypatch")
def test_new_device_logs(monkeypatch):
    logger = DummyLogger()
    client = TestHardwareAdapter(logger, "", 1234)
    device = DummyDevice()
    client.newDevice(device)
    assert any("new device" in msg for msg in logger.infos)


@pytest.mark.usefixtures("monkeypatch")
def test_new_property_logs(monkeypatch):
    logger = DummyLogger()
    client = TestHardwareAdapter(logger, "", 1234)
    prop = DummyProperty()
    client.newProperty(prop)
    assert any("new property" in msg for msg in logger.debugs)
