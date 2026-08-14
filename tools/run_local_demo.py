from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forgemesh.guarded_patch import GuardedPatch, apply_guarded_patch, sha256_text


REPO = ROOT / "demo_repo"


def now() -> str:
    return datetime.now(UTC).isoformat()


def save(directory: Path, name: str, content: dict | str) -> Path:
    path = directory / name
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic ForgeMesh RCA -> Patch -> Verify demo.")
    parser.add_argument("--scenario", default="coupon_empty_crash")
    parser.add_argument("--output", default="artifacts/TASK-001")
    args = parser.parse_args()

    scenario = json.loads((ROOT / "scenarios" / f"{args.scenario}.json").read_text(encoding="utf-8"))
    output = ROOT / args.output
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    task_id = scenario["task_id"]
    issue_artifact = {
        "artifact_id": "issue-001",
        "task_id": task_id,
        "type": "issue",
        "producer": "triage-agent",
        "created_at": now(),
        "normalized_issue": scenario["issue"],
    }
    save(output, "issue.json", issue_artifact)

    source_path = REPO / scenario["patch"]["target"]
    original_source = source_path.read_text(encoding="utf-8")
    base_hash = sha256_text(original_source)
    rca_artifact = {
        "artifact_id": "rca-001",
        "task_id": task_id,
        "type": "rca",
        "producer": "rca-agent",
        "created_at": now(),
        "root_cause": "calculate_discount indexes coupon before checking whether it is missing.",
        "confidence": 0.98,
        "evidence": [{
            "type": "source_code",
            "uri": f"repo://{scenario['patch']['target']}",
            "line_start": scenario["error_log"]["line"],
            "line_end": scenario["error_log"]["line"],
            "content_sha256": base_hash,
            "error": scenario["error_log"]["exception"],
        }],
    }
    save(output, "rca.json", rca_artifact)

    workspace = output / "workspace"
    shutil.copytree(REPO, workspace)
    patch = GuardedPatch(
        target=scenario["patch"]["target"],
        base_sha256=base_hash,
        old=scenario["patch"]["old"],
        new=scenario["patch"]["new"],
    )
    guard_result = apply_guarded_patch(workspace, patch, allowed_paths={patch.target})
    updated_source = (workspace / patch.target).read_text(encoding="utf-8")
    diff = "".join(difflib.unified_diff(
        original_source.splitlines(keepends=True),
        updated_source.splitlines(keepends=True),
        fromfile=f"a/{patch.target}",
        tofile=f"b/{patch.target}",
    ))
    patch_artifact = {
        "artifact_id": "patch-001",
        "task_id": task_id,
        "type": "patch",
        "producer": "coding-agent",
        "created_at": now(),
        "base_revision": base_hash,
        "guard": guard_result,
        "allowed_paths": [patch.target],
        "diff_file": "patch.diff",
    }
    save(output, "patch.json", patch_artifact)
    save(output, "patch.diff", diff)

    test = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--basetemp", str(workspace / ".pytest-tmp")],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    verification_artifact = {
        "artifact_id": "verification-001",
        "task_id": task_id,
        "type": "verification",
        "producer": "verification-agent",
        "created_at": now(),
        "decision": "pass" if test.returncode == 0 else "fail",
        "pytest_exit_code": test.returncode,
        "allowed_file_changes_only": True,
        "stdout": test.stdout,
        "stderr": test.stderr,
    }
    save(output, "verification.json", verification_artifact)
    knowledge = (
        "# Coupon missing-value guard\n\n"
        "- Root cause: optional request fields must be checked before dictionary access.\n"
        "- Fix pattern: return the neutral value for a missing optional coupon.\n"
        "- Verification: isolated pytest run recorded in `verification.json`.\n"
    )
    save(output, "knowledge.md", knowledge)
    save(output, "trace.json", {"task_id": task_id, "artifacts": ["issue.json", "rca.json", "patch.json", "verification.json", "knowledge.md"]})

    print(f"Artifacts written to {output}")
    print(f"Verification: {verification_artifact['decision']}")
    return test.returncode


if __name__ == "__main__":
    raise SystemExit(main())
