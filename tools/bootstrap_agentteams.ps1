[CmdletBinding()]
param(
    [string]$AgentTeamsRepo = '',
    [string]$Version = 'v1.2.2',
    [switch]$ValidateOnly
)

$ErrorActionPreference = 'Stop'
$demo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$AgentTeamsRepo = if ($AgentTeamsRepo) { $AgentTeamsRepo } else { Join-Path $PSScriptRoot '..\..\AgentTeams' }
$agentTeamsRepo = [IO.Path]::GetFullPath($AgentTeamsRepo)
$dotenv = Join-Path $demo '.env'
$runtimeDir = Join-Path $demo '.agentteams'
$envFile = Join-Path $runtimeDir 'manager.env'
$installLog = Join-Path $runtimeDir 'install-output.log'

if (-not (Test-Path -LiteralPath $dotenv)) {
    throw "Missing $dotenv. Copy .env.example to .env and fill the three LLM values."
}
if (-not (Test-Path -LiteralPath (Join-Path $agentTeamsRepo '.git'))) {
    throw "AgentTeams git checkout not found: $agentTeamsRepo"
}

function Read-DotEnv([string]$Path) {
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $index = $trimmed.IndexOf('=')
        if ($index -gt 0) {
            $key = $trimmed.Substring(0, $index).Trim()
            $value = $trimmed.Substring($index + 1).Trim().Trim('"').Trim("'")
            $values[$key] = $value
        }
    }
    return $values
}

function Add-CompatibilityFix([string]$Source) {
    $controllerArgs = @'
            "-e", "AGENTTEAMS_MATRIX_APPSERVICE_AS_TOKEN=$($config.MATRIX_APPSERVICE_AS_TOKEN)",
            "-e", "AGENTTEAMS_MATRIX_APPSERVICE_HS_TOKEN=$($config.MATRIX_APPSERVICE_HS_TOKEN)",
            "-e", "AGENTTEAMS_MINIO_USER=$($config.MINIO_USER)",
'@.TrimEnd()
    $replacements = @(
        @(
            'AGENTTEAMS_REGISTRATION_TOKEN=$($Config.REGISTRATION_TOKEN)',
            "AGENTTEAMS_REGISTRATION_TOKEN=`$(`$Config.REGISTRATION_TOKEN)`nAGENTTEAMS_MATRIX_APPSERVICE_AS_TOKEN=`$(`$Config.MATRIX_APPSERVICE_AS_TOKEN)`nAGENTTEAMS_MATRIX_APPSERVICE_HS_TOKEN=`$(`$Config.MATRIX_APPSERVICE_HS_TOKEN)"
        ),
        @(
            '    $config.MINIO_USER = if ($env:AGENTTEAMS_MINIO_USER)',
            "    `$config.MATRIX_APPSERVICE_AS_TOKEN = if (`$env:AGENTTEAMS_MATRIX_APPSERVICE_AS_TOKEN) { `$env:AGENTTEAMS_MATRIX_APPSERVICE_AS_TOKEN } else { New-RandomKey }`n    `$config.MATRIX_APPSERVICE_HS_TOKEN = if (`$env:AGENTTEAMS_MATRIX_APPSERVICE_HS_TOKEN) { `$env:AGENTTEAMS_MATRIX_APPSERVICE_HS_TOKEN } else { New-RandomKey }`n    `$config.MINIO_USER = if (`$env:AGENTTEAMS_MINIO_USER)"
        ),
        @(
            '            "-e", "AGENTTEAMS_MINIO_USER=$($config.MINIO_USER)",',
            $controllerArgs
        )
    )
    foreach ($replacement in $replacements) {
        if (-not $Source.Contains($replacement[0])) {
            throw "AgentTeams installer shape changed; compatibility anchor not found."
        }
        $Source = $Source.Replace($replacement[0], $replacement[1])
    }
    return $Source
}

$settings = Read-DotEnv $dotenv
foreach ($required in @('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL_ID')) {
    if (-not $settings[$required]) { throw "Missing $required in $dotenv" }
}

$installerLines = & git -c "safe.directory=$agentTeamsRepo" -C $agentTeamsRepo show "${Version}:install/agentteams-install.ps1"
if ($LASTEXITCODE -ne 0) { throw "Cannot read AgentTeams installer at tag $Version" }
$installer = Add-CompatibilityFix (($installerLines -join "`n") + "`n")
$tokens = $null
$parseErrors = $null
[System.Management.Automation.Language.Parser]::ParseInput($installer, [ref]$tokens, [ref]$parseErrors) | Out-Null
if ($parseErrors.Count) { throw "Patched AgentTeams installer does not parse: $($parseErrors[0].Message)" }
if ($ValidateOnly) {
    Write-Host "AgentTeams $Version installer compatibility transform validated."
    return
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$env:Path = 'C:\Users\Administrator\AppData\Local\Programs\DockerDesktop\resources\bin;' + $env:Path
$env:AGENTTEAMS_NON_INTERACTIVE = '1'
$env:AGENTTEAMS_VERSION = $Version
$env:AGENTTEAMS_LLM_PROVIDER = 'openai-compat'
$env:AGENTTEAMS_OPENAI_BASE_URL = $settings['LLM_BASE_URL']
$env:AGENTTEAMS_DEFAULT_MODEL = $settings['LLM_MODEL_ID']
$env:AGENTTEAMS_LLM_API_KEY = $settings['LLM_API_KEY']
$env:AGENTTEAMS_MANAGER_RUNTIME = 'copaw'
$env:AGENTTEAMS_MATRIX_E2EE = '0'
$env:AGENTTEAMS_MOUNT_SOCKET = '1'
$env:AGENTTEAMS_WORKSPACE_DIR = Join-Path $demo 'agentteams-manager'
if (-not (Test-Path -LiteralPath $envFile)) {
    $env:AGENTTEAMS_ADMIN_USER = 'admin'
    $env:AGENTTEAMS_ADMIN_PASSWORD = 'admin-' + [guid]::NewGuid().ToString('N').Substring(0, 16)
}

& ([scriptblock]::Create($installer)) manager -NonInteractive -EnvFile $envFile *> $installLog
Write-Host "AgentTeams $Version installation finished. Runtime config: $envFile"
Write-Host "Full installer output (contains local credentials): $installLog"
