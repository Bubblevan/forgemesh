from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKER = Path(r"C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def request(method: str, url: str, payload: dict | None = None, token: str = "") -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=headers, method=method), timeout=15) as response:
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch TASK-001 to the real AgentTeams Leader DM.")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    config = read_env(ROOT / ".agentteams" / "manager.env")
    team = subprocess.run(
        [str(DOCKER), "exec", "agentteams-controller", "agt", "get", "teams", "forgemesh-demo"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    match = re.search(r"^LeaderDMRoomID:\s+(\S+)$", team, re.MULTILINE)
    if not match:
        raise RuntimeError("forgemesh-demo has no LeaderDMRoomID")

    matrix = "http://127.0.0.1:18080"
    login = request(
        "POST",
        f"{matrix}/_matrix/client/v3/login",
        {
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": config["AGENTTEAMS_ADMIN_USER"]},
            "password": config["AGENTTEAMS_ADMIN_PASSWORD"],
        },
    )
    task = (
        "Execute TASK-001 now as a real AgentTeams workflow. Reset the mock repo, then delegate sequentially "
        "to forgemesh-rca, forgemesh-coding, and forgemesh-verifier. Each specialist must call its HTTP "
        "gateway endpoints and save the required JSON artifact. Do not simulate results. Finish only after "
        "verification.json reports decision=pass."
    )
    room = urllib.parse.quote(match.group(1), safe="")
    transaction = f"forgemesh-{time.time_ns()}"
    sent = request(
        "PUT",
        f"{matrix}/_matrix/client/v3/rooms/{room}/send/m.room.message/{transaction}",
        {"msgtype": "m.text", "body": task},
        login["access_token"],
    )
    print(f"TASK-001 sent: {sent['event_id']}")

    verification = ROOT / "artifacts" / "agentteams-live" / "TASK-001" / "verification.json"
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if verification.exists():
            result = json.loads(verification.read_text(encoding="utf-8"))
            print(f"verification decision: {result.get('decision')}")
            return 0 if result.get("decision") == "pass" else 1
        time.sleep(5)
    raise TimeoutError(f"verification artifact was not produced within {args.timeout}s")


if __name__ == "__main__":
    raise SystemExit(main())
