from flask import Flask, jsonify  # type: ignore

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/tasks", methods=["GET"])
def get_tasks():
    # Return a mock task list
    return jsonify({"tasks": [{"id": "test-task", "type": "track", "status": "pending"}]}), 200


print("Mock Citra server is running...")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

print("Mock Citra server is exited...")
