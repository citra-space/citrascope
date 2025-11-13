from abc import ABC, abstractmethod


class AbstractCitraApiClient(ABC):
    @abstractmethod
    def does_api_server_accept_key(self):
        pass

    @abstractmethod
    def get_telescope(self, telescope_id):
        pass

    @abstractmethod
    def get_satellite(self, satellite_id):
        pass

    @abstractmethod
    def get_telescope_tasks(self, telescope_id):
        pass

    @abstractmethod
    def get_ground_station(self, ground_station_id):
        pass

    @abstractmethod
    def put_telescope_status(self, body):
        """
        PUT to /telescopes to report online status.
        """
        pass
