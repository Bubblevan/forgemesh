# GuardedPatchSkill

Apply a code change only when the target is explicitly allowed, is not protected, and its current SHA-256 equals the revision captured by RCA. If a condition fails, emit `NEEDS_EVIDENCE`; do not modify the workspace.
