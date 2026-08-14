# RepoEvidenceSkill

Use `mock_issue.get` to obtain the normalized task, then use `mock_repo.get_file` for the implicated source file. Record its path, line range, and SHA-256 in the RCA artifact. Do not propose a patch when repository evidence conflicts with the error log.
