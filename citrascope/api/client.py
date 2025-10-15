import httpx

class CitraApiClient:
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
        finally:
            self.close()

    def close(self):
        self.client.close()
