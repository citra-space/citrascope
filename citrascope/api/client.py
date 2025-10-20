import httpx


class CitraApiClient:
    def __init__(self, host: str, token: str, use_ssl: bool = True, logger=None):
        self.base_url = ("https" if use_ssl else "http") + "://" + host
        self.token = token
        self.logger = logger
        self.client = httpx.Client(base_url=self.base_url, headers={"Authorization": f"Bearer {self.token}"})

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def _request(self, method: str, endpoint: str, **kwargs):
        try:
            resp = self.client.request(method, endpoint, **kwargs)
            if self.logger:
                self.logger.debug(f"{method} {endpoint}: {resp.status_code} {resp.text}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if self.logger:
                self.logger.error(f"HTTP error: {e.response.status_code} {e.response.text}")
            return None
        except Exception as e:
            if self.logger:
                self.logger.error(f"Request error: {e}")
            return None

    def does_api_server_accept_key(self):
        """Check if the API key is valid."""
        response = self._request("GET", "/auth/personal-access-tokens")
        return response is not None

    def get_telescope(self, telescope_id):
        """Check if the telescope ID is valid."""
        return self._request("GET", f"/telescopes/{telescope_id}")

    def get_satellite(self, satellite_id):
        """Fetch satellite details from /satellites/{satellite_id}"""
        return self._request("GET", f"/satellites/{satellite_id}")

    def get_telescope_tasks(self, telescope_id):
        """Fetch tasks for a given telescope."""
        return self._request("GET", f"/telescopes/{telescope_id}/tasks")

    def get_ground_station(self, ground_station_id):
        """Fetch ground station details from /ground-stations/{ground_station_id}"""
        return self._request("GET", f"/ground-stations/{ground_station_id}")
