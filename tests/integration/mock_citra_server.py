from flask import Flask, jsonify, request  # type: ignore

app = Flask(__name__)

# Track which tasks have been completed
completed_tasks = set()


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/auth/personal-access-tokens", methods=["GET"])
def check_auth():
    """Validate the personal access token."""
    return jsonify({"valid": True}), 200


@app.route("/telescopes/<telescope_id>", methods=["GET"])
def get_telescope(telescope_id):
    """Return mock telescope info."""
    return (
        jsonify(
            {
                "id": telescope_id,
                "name": "Test Telescope",
                "groundStationId": "test-ground-station-123",
                "maxSlewRate": 2.0,  # degrees per second
            }
        ),
        200,
    )


@app.route("/ground-stations/<ground_station_id>", methods=["GET"])
def get_ground_station(ground_station_id):
    """Return mock ground station info."""
    return (
        jsonify(
            {
                "id": ground_station_id,
                "name": "Test Ground Station",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "altitude": 10.0,
            }
        ),
        200,
    )


@app.route("/telescopes/<telescope_id>/tasks", methods=["GET"])
def get_telescope_tasks(telescope_id):
    """Return mock tasks for the telescope."""
    # Return a tracking task only if it hasn't been completed
    if "test-task-001" not in completed_tasks:
        return (
            jsonify(
                [
                    {
                        "id": "test-task-001",
                        "type": "Track",
                        "status": "Pending",
                        "satelliteId": "test-satellite-123",
                        "telescopeId": telescope_id,
                    }
                ]
            ),
            200,
        )
    else:
        # No more tasks
        return jsonify([]), 200


@app.route("/satellites/<satellite_id>", methods=["GET"])
def get_satellite(satellite_id):
    """Return mock satellite data with TLE."""
    return (
        jsonify(
            {
                "id": satellite_id,
                "name": "Test Satellite",
                "noradId": "25544",  # ISS NORAD ID
                "elsets": [
                    {
                        "id": "test-elset-001",
                        "creationEpoch": "2025-11-12T00:00:00Z",
                        "tle": [
                            "1 25544U 98067A   25316.50000000  .00002182  00000-0  41420-4 0  9990",
                            "2 25544  51.6461 339.8014 0001745  92.8623 267.2758 15.48919393123456",
                        ],
                    }
                ],
            }
        ),
        200,
    )


@app.route("/my/images", methods=["POST"])
def get_upload_url():
    """Return a mock signed URL for image upload."""
    filename = request.args.get("filename", "image.fits")
    return (
        jsonify(
            {
                "uploadUrl": "http://mock-storage.example.com/upload",
                "fields": {
                    "key": f"images/{filename}",
                    "policy": "mock-policy",
                },
                "resultsUrl": f"http://mock-storage.example.com/images/{filename}",
            }
        ),
        200,
    )


@app.route("/tasks/<task_id>", methods=["PUT"])
def update_task(task_id):
    """Mark a task as complete."""
    body = request.get_json()
    if body and body.get("status") == "Succeeded":
        completed_tasks.add(task_id)
        return jsonify({"id": task_id, "status": "Succeeded"}), 200
    return jsonify({"error": "Invalid request"}), 400


@app.route("/tasks", methods=["GET"])
def get_tasks():
    # Return a mock task list
    return jsonify({"tasks": [{"id": "test-task", "type": "track", "status": "pending"}]}), 200


print("Mock Citra server is running...")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

print("Mock Citra server is exited...")
