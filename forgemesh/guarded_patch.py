from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


class PatchRejectedError(ValueError):
    """Raised when a patch violates the controlled-edit policy."""


@dataclass(frozen=True)
class GuardedPatch:
    target: str
    base_sha256: str
    old: str
    new: str


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def apply_guarded_patch(
    workspace: Path,
    patch: GuardedPatch,
    *,
    allowed_paths: set[str],
    protected_prefixes: tuple[str, ...] = (".github/", "deploy/", ".env"),
) -> dict[str, str]:
    """Validate a patch against its source revision, then apply it atomically."""
    target = patch.target.replace("\\", "/")
    if target not in allowed_paths:
        raise PatchRejectedError(f"target is outside allowed scope: {target}")
    if any(target == prefix.rstrip("/") or target.startswith(prefix) for prefix in protected_prefixes):
        raise PatchRejectedError(f"target is protected: {target}")

    file_path = workspace / target
    if not file_path.is_file():
        raise PatchRejectedError(f"target file does not exist: {target}")
    source = file_path.read_text(encoding="utf-8")
    actual_sha256 = sha256_text(source)
    if actual_sha256 != patch.base_sha256:
        raise PatchRejectedError(
            "stale context: source hash changed; recollect repo evidence before editing"
        )
    if patch.old not in source:
        raise PatchRejectedError("patch precondition is absent from the current source")

    updated = source.replace(patch.old, patch.new, 1)
    file_path.write_text(updated, encoding="utf-8")
    return {
        "target": target,
        "before_sha256": actual_sha256,
        "after_sha256": sha256_text(updated),
    }
