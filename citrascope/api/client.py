import httpx

class CitraApiClient:
    def __init__(self, host: str, token: str, use_ssl: bool = True):
        self.base_url = f"{'https' if use_ssl else 'http'}://{host}"
        self.token = token
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"}
        )

    def check_api_key(self):
        resp = self.client.get("/auth/personal-access-tokens")
        return resp

    def close(self):
        self.client.close()
