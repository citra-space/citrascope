import os

import httpx

from .abstract_api_client import AbstractCitraApiClient


class CitraApiClient(AbstractCitraApiClient):
    def put_telescope_status(self, body):
        """
        PUT to /telescopes to report online status.
        """
        try:
            response = self._request("PUT", "/telescopes", json=body)
            if self.logger:
                self.logger.debug(f"PUT /telescopes: {response}")
            return response
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed PUT /telescopes: {e}")
            return None

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
                # Check if response is HTML (e.g., Cloudflare error pages)
                content_type = e.response.headers.get("content-type", "")
                response_text = e.response.text

                if "text/html" in content_type or response_text.strip().startswith("<"):
                    # Log only status and a brief message for HTML responses, sometimes we get Cloudflare error pages
                    self.logger.error(
                        f"HTTP error: {e.response.status_code} - "
                        f"Received HTML error page (likely Cloudflare or server error) for {method} {endpoint}"
                    )
                else:
                    # Log full response for non-HTML errors (JSON, plain text, etc.)
                    self.logger.error(f"HTTP error: {e.response.status_code} {response_text}")
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

    def upload_image(self, task_id, telescope_id, filepath):
        """Upload an image file for a given task."""
        file_size = os.path.getsize(filepath)
        signed_url_response = self._request(
            "POST",
            f"/my/images?filename=citra_task_{task_id}_image.fits&telescope_id={telescope_id}&task_id={task_id}&file_size={file_size}",
        )
        if not signed_url_response or "uploadUrl" not in signed_url_response:
            if self.logger:
                self.logger.error("Failed to get signed URL for image upload.")
            return None

        upload_url = signed_url_response["uploadUrl"]
        fields = signed_url_response["fields"]

        # Prepare the multipart form data
        files = {"file": (os.path.basename(filepath), open(filepath, "rb"), "application/fits")}
        data = fields  # Fields provided in the signed URL response

        # Perform the POST request to upload the file
        try:
            response = httpx.post(upload_url, data=data, files=files)
            if self.logger:
                self.logger.debug(f"Image upload response: {response.status_code} {response.text}")
            response.raise_for_status()
            return signed_url_response.get("resultsUrl")  # Return the results URL if needed
        except httpx.RequestError as e:
            if self.logger:
                self.logger.error(f"Failed to upload image: {e}")
            return None
        finally:
            # Ensure the file is closed after the upload
            files["file"][1].close()

    def mark_task_complete(self, task_id):
        """Mark a task as complete using the API."""
        try:
            body = {"status": "Succeeded"}
            response = self._request("PUT", f"/tasks/{task_id}", json=body)
            if self.logger:
                self.logger.debug(f"Marked task {task_id} as complete: {response}")
            return response
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to mark task {task_id} as complete: {e}")
            return None

    def mark_task_failed(self, task_id):
        """Mark a task as failed using the API."""
        try:
            body = {"status": "Failed"}
            response = self._request("PUT", f"/tasks/{task_id}", json=body)
            if self.logger:
                self.logger.debug(f"Marked task {task_id} as failed: {response}")
            return response
        except Exception as e:
            if self.logger:
                self.logger.error(f"Failed to mark task {task_id} as failed: {e}")
            return None
