[CmdletBinding()]
param(
    [string]$Model = ''
)

$ErrorActionPreference = 'Stop'
$docker = 'C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\resources\bin\docker.exe'
$base = 'http://host.docker.internal:18089/tools/coupon_empty_crash'

if (-not (Test-Path -LiteralPath $docker)) { throw "Docker CLI not found: $docker" }
if (-not $Model) {
    $demo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
    $line = Get-Content -LiteralPath (Join-Path $demo '.env') | Where-Object { $_ -match '^LLM_MODEL_ID=' } | Select-Object -First 1
    $Model = ($line -split '=', 2)[1].Trim()
}
if (-not $Model) { throw 'Model is empty' }

$identities = @{
    'forgemesh-leader' = "You are the ForgeMesh Team Leader. Coordinate TASK-001 strictly in order: reset using POST $base/mock_repo.reset, delegate RCA to forgemesh-rca, pass evidence to forgemesh-coding, then ask forgemesh-verifier to run independent tests. Never edit code yourself. Require rca.json, patch.json, and verification.json. Report success only when decision=pass."
    'forgemesh-rca' = "You are the read-only RCA specialist. Call POST $base/mock_issue.get and $base/mock_repo.get_file. Identify the exact crash line and source SHA-256. Never modify files. Save rca.json through $base/mock_artifact.put and report evidence to the Leader."
    'forgemesh-coding' = "You are the guarded Coding specialist. Consume RCA and fetch fresh source. The only mutation is POST $base/mock_repo.apply_guarded_patch with path, base_sha256, old, new. Keep the diff minimal. Save patch.json through mock_artifact.put. Do not run tests."
    'forgemesh-verifier' = "You are the independent Verification specialist. Never edit code. Call POST $base/mock_ci.run_tests, inspect exit_code/stdout/decision, save verification.json through mock_artifact.put, and report pass or fail."
}

$current = (& $docker exec agentteams-controller agt get workers -o json | ConvertFrom-Json).workers
foreach ($name in @('forgemesh-leader', 'forgemesh-rca', 'forgemesh-coding', 'forgemesh-verifier')) {
    if ($current.name -contains $name) {
        Write-Host "$name already exists"
        continue
    }
    & $docker exec agentteams-controller agt create worker --name $name --model $Model --runtime copaw --identity $identities[$name] --no-wait
    if ($LASTEXITCODE -ne 0) { throw "Failed to create $name" }
}

$deadline = (Get-Date).AddMinutes(4)
do {
    $workers = (& $docker exec agentteams-controller agt get workers -o json | ConvertFrom-Json).workers |
        Where-Object { $_.name -like 'forgemesh-*' }
    $notReady = $workers | Where-Object { $_.phase -ne 'Running' }
    if ($workers.Count -eq 4 -and -not $notReady) { break }
    Start-Sleep -Seconds 5
} while ((Get-Date) -lt $deadline)
if ($workers.Count -ne 4 -or $notReady) { throw 'ForgeMesh workers did not all reach Running within four minutes' }

& $docker exec agentteams-controller agt get teams forgemesh-demo *> $null
if ($LASTEXITCODE -ne 0) {
    & $docker exec agentteams-controller agt create team --name forgemesh-demo --leader-name forgemesh-leader --workers forgemesh-rca,forgemesh-coding,forgemesh-verifier --description 'Artifact-first local RCA to guarded patch to independent pytest verification'
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create forgemesh-demo team' }
}

& $docker exec agentteams-controller agt get teams forgemesh-demo
