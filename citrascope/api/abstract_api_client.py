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

    @abstractmethod
    def expand_filters(self, filter_names):
        """
        POST to /filters/expand to expand filter names to spectral specs.
        """
        pass

    @abstractmethod
    def update_telescope_spectral_config(self, telescope_id, spectral_config):
        """
        PATCH to /telescopes to update telescope's spectral configuration.
        """
        pass
