"""End-to-end FastAPI -> SQLite persistence test.

Place this file in your project's backend/ folder and run:
    python test_api_sqlite_restart.py

Creates ONE real test incident in backend/data/itsm.db. Does NOT delete or reset data.
For reliable testing, stop any other FastAPI process using the same SQLite database first.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND = Path(__file__).resolve().parent
BASE_HOST = "127.0.0.1"
LOGIN_EMAIL = os.getenv("ITSM_TEST_EMAIL", "ravi@corp.in")
LOGIN_PASSWORD = os.getenv("ITSM_TEST_PASSWORD", "Passw0rd!")
STARTUP_TIMEOUT_SECONDS = 30


class TestFailure(Exception):
    pass


def get_unused_port():
    with socket.socket() as s:
        s.bind((BASE_HOST, 0))
        return s.getsockname()[1]


def api_request(base_url, method, route, *, token=None, payload=None):
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(base_url + route, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TestFailure(f"{method} {route} returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise TestFailure(f"Could not reach {base_url}: {exc}") from exc


def start_server(port, log_handle):
    command = [
        sys.executable, "-m", "uvicorn", "api.main:app",
        "--host", BASE_HOST, "--port", str(port),
    ]
    process = subprocess.Popen(
        command,
        cwd=BACKEND,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    base_url = f"http://{BASE_HOST}:{port}"
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise TestFailure("FastAPI failed to start. See server log below.")
        try:
            status, schema = api_request(base_url, "GET", "/openapi.json")
            if status == 200 and isinstance(schema, dict):
                return process, base_url
        except TestFailure:
            pass
        time.sleep(0.25)
    raise TestFailure("FastAPI did not become ready within 30 seconds.")


def stop_server(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=12)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def login(base_url):
    status, result = api_request(base_url, "POST", "/api/auth/login", payload={
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD,
    })
    if status != 200 or not isinstance(result, dict) or not result.get("token"):
        raise TestFailure(f"Login returned unexpected data: HTTP {status}, {result}")
    return result["token"]


def get_my_incidents(base_url, token):
    status, result = api_request(base_url, "GET", "/api/incidents/mine", token=token)
    if status != 200 or not isinstance(result, list):
        raise TestFailure(f"Incident list returned unexpected data: HTTP {status}, {result}")
    return result


def ensure_incident_exists(incidents, incident_id):
    return next(
        (incident for incident in incidents
         if isinstance(incident, dict) and incident.get("incidentId") == incident_id),
        None,
    )


def show_server_log(log_file):
    log_file.flush()
    with open(log_file.name, "r", encoding="utf-8", errors="replace") as stream:
        lines = stream.readlines()[-35:]
    if lines:
        print("\n--- Last server log lines ---")
        print("".join(lines).rstrip())
        print("--- End of log ---")


def main():
    if not (BACKEND / "api" / "main.py").is_file():
        print("FAIL: Put this script in the backend/ folder (beside api/ and itsm/).")
        return 1

    db_path = BACKEND / "data" / "itsm.db"
    print(f"Working folder: {BACKEND}")
    print(f"Expected SQLite file: {db_path}")
    if not db_path.is_file():
        print("FAIL: data/itsm.db is missing. Run: python -m itsm.api.init_db")
        return 1

    print("NOTE: This test adds one real incident to the existing database.")
    print("NOTE: Stop any other FastAPI server using data/itsm.db before running.")
    port = get_unused_port()
    process = None

    with tempfile.NamedTemporaryFile(mode="w+", prefix="itsm_api_test_", suffix=".log", delete=True) as log_file:
        try:
            print("\n[1/7] Starting FastAPI on a temporary local port...")
            process, base_url = start_server(port, log_file)
            print(f"PASS: Server is ready at {base_url}")

            print("[2/7] Logging in as sample employee...")
            token = login(base_url)
            print("PASS: Login returned a JWT")

            print("[3/7] Creating an incident through the REAL API...")
            title = "SQLite restart check " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            status, created = api_request(base_url, "POST", "/api/incidents", token=token, payload={
                "title": title,
                "description": "Automated persistence test. This incident must survive an API restart.",
                "serviceId": "SVC-PAY",
                "impact": "HIGH",
                "urgency": "HIGH",
                "affectedUsers": 20,
                "category": None,
            })
            if status != 201 or not isinstance(created, dict) or not created.get("incidentId"):
                raise TestFailure(f"Create returned unexpected data: HTTP {status}, {created}")
            incident_id = created["incidentId"]
            print(f"PASS: Incident {incident_id} created (HTTP 201)")

            print("[4/7] Checking the incident is returned before restart...")
            before = ensure_incident_exists(get_my_incidents(base_url, token), incident_id)
            if not before:
                raise TestFailure(f"Incident {incident_id} was NOT returned before restart")
            print("PASS: Same incident found before restart")

            print("[5/7] Shutting down FastAPI completely...")
            stop_server(process)
            process = None
            print("PASS: Server stopped")

            print("[6/7] Starting a FRESH FastAPI process with the same database...")
            process, base_url = start_server(port, log_file)
            new_token = login(base_url)
            print("PASS: Server restarted and fresh login worked")

            print("[7/7] Looking for the SAME incident ID after restart...")
            after = ensure_incident_exists(get_my_incidents(base_url, new_token), incident_id)
            if not after:
                raise TestFailure(f"Incident {incident_id} disappeared after restart! Database integration is NOT confirmed.")
            if after.get("title") != title:
                raise TestFailure(f"Incident {incident_id} survived, but its title changed unexpectedly")
            print(f"PASS: Incident {incident_id} and its title persisted across restart")
            print("\n========== ALL CHECKS PASSED ==========")
            print("FastAPI -> SQLite -> FastAPI persistence verified.")
            print(f"Saved incident: {incident_id}")
            print(f"Database: {db_path}")
            return 0

        except (TestFailure, OSError, ValueError) as exc:
            print(f"\nFAIL: {exc}")
            show_server_log(log_file)
            return 1
        finally:
            stop_server(process)


if __name__ == "__main__":
    sys.exit(main())
