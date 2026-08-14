# ForgeMesh Demo

本地优先的 GOAI 软件研发协同 MVP：由真实 AgentTeams Team 完成
`Issue → RCA → Guarded Patch → Independent Verification → Knowledge` 闭环。

当前稳定基线：Windows + Docker Desktop + AgentTeams `v1.2.2` + CoPaw + Python 3.12/uv。

## MVP 里有什么

- `demo_repo/`：故意带 `coupon=None` 崩溃的 Python 项目和 2 个 pytest。
- `tools/mock_gateway.py`：本机 issue/repo/test/artifact gateway。
- `forgemesh/guarded_patch.py`：文件白名单、源 SHA-256、受保护路径和 stale-context guard。
- 四个 Agent：Leader、RCA、Coding、Verifier；只有 Coding 能走受控 patch 接口。
- `evidence/TASK-001/`：真实 Matrix-mediated 运行产生的脱敏 RCA、Patch、Verification 证据。
- 三个可复用 Skills：repo evidence、guarded patch、verification。

## 0. Python 本地闭环

```powershell
cd D:\MyLab\harness\GOAI\forgemesh-demo
uv sync
uv run pytest
uv run python tools/run_local_demo.py
```

`run_local_demo.py` 在忽略的 `artifacts/TASK-001/workspace` 中复制 demo repo，不会修掉原始故障样例。

## 1. 配置

```powershell
Copy-Item .env.example .env
```

填写：

```dotenv
LLM_API_KEY=...
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_MODEL_ID=your-model-id
```

`.env`、`.agentteams/`、`agentteams-manager/` 和原始运行 artifacts 均不会进入 Git。

## 2. 安装固定版本 AgentTeams

先把官方 AgentTeams checkout 放在本项目同级的 `../AgentTeams`，并确保 Docker Desktop 已启动：

```powershell
powershell -ExecutionPolicy Bypass -File tools/bootstrap_agentteams.ps1
```

脚本固定使用 `v1.2.2`，并在内存中补上该 tag 的 Windows installer 遗漏的两个 Matrix AppService token。完整安装输出可能包含本机生成的管理员凭据，因此只写入忽略目录 `.agentteams/install-output.log`。

安装验收：

```powershell
docker exec agentteams-controller agt get managers default
```

预期 `Phase: Running`、`Runtime: copaw`、镜像 tag 为 `v1.2.2`。

## 3. 启动 gateway 并创建 Team

终端 A：

```powershell
uv run python tools/mock_gateway.py
```

终端 B：

```powershell
powershell -ExecutionPolicy Bypass -File tools/create_forgemesh_team.ps1
```

脚本创建：

- `forgemesh-leader`
- `forgemesh-rca`
- `forgemesh-coding`
- `forgemesh-verifier`
- Team `forgemesh-demo`

Docker Worker 使用 `http://host.docker.internal:18089` 访问宿主机 gateway。

## 4. 派发真实 AgentTeams 任务

```powershell
uv run python tools/dispatch_agentteams_demo.py --timeout 600
```

脚本从忽略的 `.agentteams/manager.env` 读取本机 Matrix 管理员凭据，通过 Leader DM 派发 TASK-001，并等待：

```text
artifacts/agentteams-live/TASK-001/rca.json
artifacts/agentteams-live/TASK-001/patch.json
artifacts/agentteams-live/TASK-001/verification.json
```

成功条件是 `verification.json` 的 `decision` 为 `pass`。可以独立复核 live workspace：

```powershell
uv run pytest artifacts/agentteams-live/TASK-001/workspace/tests
```

## Gateway 契约

所有 POST 路径前缀：`/tools/coupon_empty_crash/`。

| Tool | 权限/作用 |
|---|---|
| `mock_repo.reset` | 创建隔离 workspace |
| `mock_issue.get` | 读取 issue 与错误日志 |
| `mock_repo.get_file` | 只允许读取场景白名单文件 |
| `mock_repo.apply_guarded_patch` | 校验文件、base SHA、old 片段与变更预算后写入 |
| `mock_ci.run_tests` | 在隔离 workspace 真实运行 pytest |
| `mock_artifact.put` | 只允许写入已声明的 JSON artifact 名称 |

健康检查：`GET /health`；本次进程内调用轨迹：`GET /trace`。

## 已验证结果

- 项目测试：`4 passed`
- 原始 bug：`TypeError: 'NoneType' object is not subscriptable`
- AgentTeams：Team Active，Leader ready，Workers `3/3`
- Guarded patch：只改 `discounts.py`，源/目标 SHA 均落盘
- Verifier：`2 passed`，`decision=pass`

脱敏证据见 [`evidence/TASK-001`](evidence/TASK-001)。
