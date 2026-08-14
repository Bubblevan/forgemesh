from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forgemesh.guarded_patch import GuardedPatch, apply_guarded_patch, sha256_text


TRACE: list[dict] = []
TRACE_LOCK = threading.Lock()
REPO = ROOT / "demo_repo"
RUNTIME = ROOT / "artifacts" / "agentteams-live"
ALLOWED_ARTIFACTS = {"issue.json", "rca.json", "patch.json", "verification.json", "knowledge.json"}


def scenario_data(scenario_id: str) -> dict:
    return json.loads((ROOT / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8"))


def scenario_workspace(scenario: dict) -> Path:
    return RUNTIME / scenario["task_id"] / "workspace"


def reset_workspace(scenario: dict) -> dict:
    task_root = RUNTIME / scenario["task_id"]
    if task_root.exists():
        shutil.rmtree(task_root)
    workspace = task_root / "workspace"
    shutil.copytree(REPO, workspace)
    with TRACE_LOCK:
        TRACE.clear()
    return {"task_id": scenario["task_id"], "workspace_ready": True}


def execute_tool(scenario_id: str, tool: str, payload: dict) -> dict:
    scenario = scenario_data(scenario_id)
    workspace = scenario_workspace(scenario)
    if tool == "mock_repo.reset":
        return reset_workspace(scenario)
    if tool == "mock_issue.get":
        return scenario["issue"] | {"task_id": scenario["task_id"], "error_log": scenario["error_log"]}
    if not workspace.exists():
        raise ValueError("workspace is not initialized; call mock_repo.reset first")
    if tool == "mock_repo.get_file":
        target = payload.get("path", scenario["patch"]["target"])
        if target != scenario["patch"]["target"]:
            raise ValueError(f"path is not allowed: {target}")
        source = (workspace / target).read_text(encoding="utf-8")
        return {"path": target, "content": source, "sha256": sha256_text(source)}
    if tool == "mock_repo.apply_guarded_patch":
        expected = scenario["patch"]
        target = payload.get("path", expected["target"])
        if target != expected["target"]:
            raise ValueError(f"path is not allowed: {target}")
        old = payload.get("old")
        new = payload.get("new")
        if not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
            raise ValueError("old and new must be distinct non-empty strings")
        path = workspace / target
        before = path.read_text(encoding="utf-8")
        if old not in before:
            raise ValueError("patch precondition is absent from the current source")
        candidate = before.replace(old, new, 1)
        changed_lines = [
            line
            for line in difflib.ndiff(before.splitlines(), candidate.splitlines())
            if line.startswith(("+ ", "- "))
        ]
        if len(changed_lines) > 6:
            raise ValueError("patch exceeds the six-line guarded change budget")
        guard = apply_guarded_patch(
            workspace,
            GuardedPatch(target=target, base_sha256=payload["base_sha256"], old=old, new=new),
            allowed_paths={expected["target"]},
        )
        after = path.read_text(encoding="utf-8")
        diff = "".join(difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{target}",
            tofile=f"b/{target}",
        ))
        return {"path": target, "guard": guard, "diff": diff}
    if tool == "mock_ci.run_tests":
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "--basetemp", str(workspace / ".pytest-tmp")],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "command": "python -m pytest tests",
            "exit_code": completed.returncode,
            "decision": "pass" if completed.returncode == 0 else "fail",
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    if tool == "mock_artifact.put":
        name = payload.get("name")
        content = payload.get("content")
        if name not in ALLOWED_ARTIFACTS or not isinstance(content, dict):
            raise ValueError("artifact name or content is not allowed")
        artifact_path = RUNTIME / scenario["task_id"] / name
        artifact_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"name": name, "saved": True}
    raise ValueError(f"unknown tool: {tool}")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self.reply(HTTPStatus.OK, {"ok": True, "service": "forgemesh-mock-gateway"})
        elif path == "/trace":
            with TRACE_LOCK:
                trace = list(TRACE)
            self.reply(HTTPStatus.OK, {"ok": True, "result": trace})
        else:
            self.reply(HTTPStatus.NOT_FOUND, {"ok": False, "error": "unknown endpoint"})

    def do_POST(self) -> None:  # noqa: N802
        parts = [item for item in urlparse(self.path).path.strip("/").split("/") if item]
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        try:
            if len(parts) != 3 or parts[0] != "tools":
                raise ValueError("expected /tools/{scenario_id}/{tool_name}")
            tool = parts[2]
            result = execute_tool(parts[1], tool, payload)
            with TRACE_LOCK:
                TRACE.append({"tool": tool, "scenario": parts[1], "payload": payload, "result": result})
            self.reply(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:  # demo gateway intentionally returns structured errors
            self.reply(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(fmt % args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18089)
    args = parser.parse_args()
    print(f"ForgeMesh mock gateway: http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
