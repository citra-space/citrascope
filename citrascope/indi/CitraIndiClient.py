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
        self.logger.info(f"new device {d.getDeviceName()}")
        # TODO: if it's the scope we want, set our_scope

    def removeDevice(self, d):
        """Emmited when a device is deleted from INDI server."""
        self.logger.info(f"remove device {d.getDeviceName()}")
        # TODO: if it's our_scope, set our_scope to None, and react accordingly

    def newProperty(self, p):
        """Emmited when a new property is created for an INDI driver."""
        self.logger.debug(f"new property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def updateProperty(self, p):
        """Emmited when a new property value arrives from INDI server."""
        self.logger.debug(f"update property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")
        if self.our_scope is not None and p.getDeviceName() == self.our_scope.getDeviceName():
            value = None
            changed_type = p.getTypeAsString()
            if changed_type == "INDI_TEXT":
                value = self.our_scope.getText(p.getName())[0].value
            if changed_type == "INDI_NUMBER":
                value = self.our_scope.getNumber(p.getName())[0].value
            self.logger.debug(f"Scope '{self.our_scope.getDeviceName()}' property {p.getName()} updated value: {value}")

    def removeProperty(self, p):
        """Emmited when a property is deleted for an INDI driver."""
        self.logger.debug(f"remove property {p.getName()} as {p.getTypeAsString()} for device {p.getDeviceName()}")

    def newMessage(self, d, m):
        """Emmited when a new message arrives from INDI server."""
        self.logger.debug(f"new Message {d.messageQueue(m)}")

    def serverConnected(self):
        """Emmited when the server is connected."""
        self.logger.info(f"INDI Server connected ({self.getHost()}:{self.getPort()})")

    def serverDisconnected(self, code):
        """Emmited when the server gets disconnected."""
        self.logger.info(f"INDI Server disconnected (exit code = {code},{self.getHost()}:{self.getPort()})")
