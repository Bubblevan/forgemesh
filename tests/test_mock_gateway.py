from __future__ import annotations

import json
from pathlib import Path

from tools import mock_gateway


def test_gateway_runs_guarded_patch_and_real_pytest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mock_gateway, "RUNTIME", tmp_path / "runtime")
    scenario_id = "coupon_empty_crash"

    reset = mock_gateway.execute_tool(scenario_id, "mock_repo.reset", {})
    source = mock_gateway.execute_tool(scenario_id, "mock_repo.get_file", {"path": "discounts.py"})
    scenario = json.loads(
        (mock_gateway.ROOT / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8")
    )
    patch = mock_gateway.execute_tool(
        scenario_id,
        "mock_repo.apply_guarded_patch",
        {
            "path": "discounts.py",
            "base_sha256": source["sha256"],
            "old": scenario["patch"]["old"],
            "new": scenario["patch"]["new"],
        },
    )
    verification = mock_gateway.execute_tool(scenario_id, "mock_ci.run_tests", {})

    assert reset == {"task_id": "TASK-001", "workspace_ready": True}
    assert patch["guard"]["before_sha256"] != patch["guard"]["after_sha256"]
    assert verification["exit_code"] == 0
    assert verification["decision"] == "pass"


def test_gateway_rejects_unapproved_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mock_gateway, "RUNTIME", tmp_path / "runtime")
    scenario_id = "coupon_empty_crash"
    mock_gateway.execute_tool(scenario_id, "mock_repo.reset", {})

    try:
        mock_gateway.execute_tool(
            scenario_id,
            "mock_repo.get_file",
            {"path": "../scenarios/coupon_empty_crash.json"},
        )
    except ValueError as exc:
        assert "path is not allowed" in str(exc)
    else:
        raise AssertionError("unapproved path should have been rejected")
