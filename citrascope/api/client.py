import httpx

class CitraApiClient:
    def get_telescope_tasks(self, telescope_id):
        try:
            resp = self.client.get(f"/telescopes/{telescope_id}/tasks")
            if self.logger:
                # self.logger.info(f"Tasks fetch response: {resp.status_code} {resp.text}")
                pass
            if resp.status_code == 200:
                self.logger.info(f"Found {len(resp.json())} tasks from API.")
                return resp.json()
            else:
                return []
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error fetching tasks: {e}")
            return []
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __del__(self):
        self.close()

    def close(self):
        if hasattr(self, 'client') and self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None

    def __init__(self, host: str, token: str, use_ssl: bool = True, logger=None):
        self.base_url = f"{'https' if use_ssl else 'http'}://{host}"
        self.token = token
        self.logger = logger
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"}
        )

    def check_api_key(self):
        try:
            resp = self.client.get("/auth/personal-access-tokens")
            if self.logger:
                self.logger.info(f"API key check response: {resp.status_code} {resp.text}")
            if resp.status_code == 200:
                if self.logger:
                    self.logger.info("API key is valid. Connected to Citra API.")
                return True
            else:
                if self.logger:
                    self.logger.error(f"API key check failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error connecting to Citra API: {e}")
            return False

    def check_telescope_id(self, telescope_id):
        try:
            resp = self.client.get(f"/telescopes/{telescope_id}")
            if self.logger:
                self.logger.info(f"Telescope check response: {resp.status_code} {resp.text}")
            if resp.status_code == 200:
                if self.logger:
                    self.logger.info("Telescope ID is valid.")
                return True
            else:
                if self.logger:
                    self.logger.error(f"Telescope ID check failed: {resp.status_code} {resp.text}")
                return False
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error checking telescope ID: {e}")
            return False