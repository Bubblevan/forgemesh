from pathlib import Path

import pytest

from forgemesh.guarded_patch import GuardedPatch, PatchRejectedError, apply_guarded_patch, sha256_text


def test_guarded_patch_rejects_stale_context(tmp_path: Path) -> None:
    target = tmp_path / "discounts.py"
    target.write_text("value = 1\n", encoding="utf-8")
    patch = GuardedPatch("discounts.py", sha256_text("value = 0\n"), "value = 0", "value = 2")

    with pytest.raises(PatchRejectedError, match="stale context"):
        apply_guarded_patch(tmp_path, patch, allowed_paths={"discounts.py"})


def test_guarded_patch_applies_only_to_approved_file(tmp_path: Path) -> None:
    target = tmp_path / "discounts.py"
    source = "value = 0\n"
    target.write_text(source, encoding="utf-8")
    patch = GuardedPatch("discounts.py", sha256_text(source), "value = 0", "value = 1")

    apply_guarded_patch(tmp_path, patch, allowed_paths={"discounts.py"})
    assert target.read_text(encoding="utf-8") == "value = 1\n"
