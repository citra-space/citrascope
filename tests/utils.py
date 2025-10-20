class DummyLogger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.debugs = []

    def info(self, msg):
        self.infos.append(msg)

    def error(self, msg):
        self.errors.append(msg)

    def debug(self, msg):
        self.debugs.append(msg)
