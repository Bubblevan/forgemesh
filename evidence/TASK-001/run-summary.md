# TASK-001 MVP evidence

- Run date: 2026-08-14
- Runtime: AgentTeams `v1.2.2`, CoPaw Manager and four CoPaw Workers
- Team: `forgemesh-demo`, Active, Leader ready, Workers ready `3/3`
- Workflow: Leader → RCA → Coding → Verifier
- Repository policy: isolated workspace, one allowed source file, SHA-256 stale-context rejection, six-line change budget
- Verification: independent gateway pytest plus an external repeat, both `2 passed`

The committed JSON files are curated, secret-free copies of the artifacts produced by the live Matrix-mediated run. Raw runtime state remains under ignored `artifacts/` and `.agentteams/` directories.
