import PyIndi


# The IndiClient class which inherits from the module PyIndi.BaseClient class
# Note that all INDI constants are accessible from the module as PyIndi.CONSTANTNAME
class CitraIndiClient(PyIndi.BaseClient):

    our_scope = None

    def __init__(self, CITRA_LOGGER):
        super(CitraIndiClient, self).__init__()
        self.logger = CITRA_LOGGER
        self.logger.debug("creating an instance of IndiClient")

    def newDevice(self, d):
        """Emmited when a new device is created from INDI server."""
        self.logger.debug(f"new device {d.getDeviceName()}")

    def removeDevice(self, d):
        """Emmited when a device is deleted from INDI server."""
        self.logger.debug(f"remove device {d.getDeviceName()}")

    def newProperty(self, p):
        """Emmited when a new property is created for an INDI driver."""
        self.logger.debug(f"new property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def updateProperty(self, p):
        """Emmited when a new property value arrives from INDI server."""
        self.logger.debug(f"update property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def removeProperty(self, p):
        """Emmited when a property is deleted for an INDI driver."""
        self.logger.debug(f"remove property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def newMessage(self, d, m):
        """Emmited when a new message arrives from INDI server."""
        self.logger.debug(f"new Message {d.messageQueue(m)}")

    def serverConnected(self):
        """Emmited when the server is connected."""
        self.logger.debug(f"INDI Server connected ({self.getHost()}:{self.getPort()})")

    def serverDisconnected(self, code):
        """Emmited when the server gets disconnected."""
        self.logger.debug(f"INDI Server disconnected (exit code = {code},{self.getHost()}:{self.getPort()})")
