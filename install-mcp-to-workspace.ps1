# Kanbanger MCP Workspace Installer
# Installs Kanbanger MCP server configuration to the current workspace
# Usage: powershell -ExecutionPolicy Bypass -File install-mcp-to-workspace.ps1

$ErrorActionPreference = "Stop"

Write-Host "===========================================`n" -ForegroundColor Cyan
Write-Host "  Kanbanger MCP Workspace Installer`n" -ForegroundColor Cyan
Write-Host "===========================================`n" -ForegroundColor Cyan

# Get current workspace directory
$workspaceRoot = Get-Location
Write-Host "Workspace: $workspaceRoot`n" -ForegroundColor Yellow

# Check if _kanban.md exists
$kanbanFile = Join-Path $workspaceRoot "_kanban.md"
if (-not (Test-Path $kanbanFile)) {
    Write-Host "WARNING: No _kanban.md found in workspace!" -ForegroundColor Red
    Write-Host "The MCP server will install, but won't work until you create a kanban board.`n" -ForegroundColor Yellow
    
    $create = Read-Host "Create example _kanban.md now? (y/n)"
    if ($create -eq 'y' -or $create -eq 'Y') {
        $exampleKanban = @"
# Project Kanban Board

## BACKLOG
*   [ ] Example future task

## TODO
*   [ ] Example task ready to start

## DOING

## DONE
*   [x] Set up kanbanger MCP server
"@
        Set-Content -Path $kanbanFile -Value $exampleKanban -Encoding UTF8
        Write-Host "Created example _kanban.md`n" -ForegroundColor Green
    }
}

# Create .cursor directory if it doesn't exist
$cursorDir = Join-Path $workspaceRoot ".cursor"
if (-not (Test-Path $cursorDir)) {
    New-Item -ItemType Directory -Path $cursorDir | Out-Null
    Write-Host "Created .cursor directory" -ForegroundColor Green
}

# Check if mcp.json already exists
$mcpConfigPath = Join-Path $cursorDir "mcp.json"
if (Test-Path $mcpConfigPath) {
    Write-Host "WARNING: .cursor/mcp.json already exists!" -ForegroundColor Yellow
    Write-Host "Backing up to .cursor/mcp.json.backup`n" -ForegroundColor Yellow
    Copy-Item $mcpConfigPath "$mcpConfigPath.backup" -Force
}

# Get the kanbanger installation directory (where this script is)
$kanbangerRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# Check for .env file and read values
$envFile = Join-Path $workspaceRoot ".env"
$githubToken = "your_github_token_here"
$githubRepo = "owner/repo"
$githubProjectNumber = ""

if (Test-Path $envFile) {
    Write-Host "Reading credentials from .env file..." -ForegroundColor Cyan
    $envContent = Get-Content $envFile
    
    foreach ($line in $envContent) {
        if ($line -match '^GITHUB_TOKEN=(.+)') {
            $githubToken = $matches[1]
        }
        elseif ($line -match '^GITHUB_REPO=(.+)') {
            $githubRepo = $matches[1]
        }
        elseif ($line -match '^GITHUB_PROJECT_NUMBER=(.+)') {
            $githubProjectNumber = $matches[1]
        }
    }
    Write-Host "Loaded credentials from .env" -ForegroundColor Green
} else {
    Write-Host "WARNING: No .env file found!" -ForegroundColor Red
    Write-Host "MCP config will be created with placeholder values.`n" -ForegroundColor Yellow
}

# Create MCP configuration with actual values (not ${env:VAR} placeholders)
$mcpConfig = @{
    mcpServers = @{
        kanbanger = @{
            command = "python"
            args = @("-m", "kanbanger_mcp")
            env = @{
                KANBANGER_WORKSPACE = "`${workspaceFolder}"
                GITHUB_TOKEN = $githubToken
                GITHUB_REPO = $githubRepo
                GITHUB_PROJECT_NUMBER = $githubProjectNumber
            }
        }
    }
}

# Convert to JSON and save
$mcpConfig | ConvertTo-Json -Depth 10 | Set-Content -Path $mcpConfigPath -Encoding UTF8
Write-Host "Created .cursor/mcp.json with workspace configuration`n" -ForegroundColor Green

if (-not (Test-Path $envFile)) {
    Write-Host "GITHUB_TOKEN=your_token_here" -ForegroundColor Gray
    Write-Host "GITHUB_REPO=owner/repo" -ForegroundColor Gray
    Write-Host "GITHUB_PROJECT_NUMBER=6  # optional`n" -ForegroundColor Gray
    
    $createEnv = Read-Host "Create template .env now? (y/n)"
    if ($createEnv -eq 'y' -or $createEnv -eq 'Y') {
        $envTemplate = @"
# GitHub Configuration for Kanbanger
GITHUB_TOKEN=your_github_token_here
GITHUB_REPO=owner/repo
GITHUB_PROJECT_NUMBER=  # optional, will auto-detect
"@
        Set-Content -Path $envFile -Value $envTemplate -Encoding UTF8
        Write-Host "Created .env template - EDIT IT with your credentials!`n" -ForegroundColor Green
    }
}

# Check .gitignore and add .cursor/mcp.json if needed
$gitignorePath = Join-Path $workspaceRoot ".gitignore"
if (Test-Path $gitignorePath) {
    $gitignoreContent = Get-Content $gitignorePath -Raw
    if ($gitignoreContent -notmatch "\.cursor/mcp\.json") {
        Add-Content $gitignorePath "`n# Cursor MCP config with secrets`n.cursor/mcp.json"
        Write-Host "Added .cursor/mcp.json to .gitignore" -ForegroundColor Green
    }
} else {
    Write-Host "WARNING: No .gitignore found - remember not to commit .cursor/mcp.json!" -ForegroundColor Yellow
}

Write-Host "`n===========================================`n" -ForegroundColor Cyan
Write-Host "Installation Complete!`n" -ForegroundColor Green
Write-Host "Next Steps:" -ForegroundColor Cyan
if (Test-Path $envFile) {
    Write-Host "1. Restart Cursor to load the MCP server" -ForegroundColor White
    Write-Host "2. Verify by asking AI: 'What MCP tools do you have?'`n" -ForegroundColor White
} else {
    Write-Host "1. Create .env with your GitHub credentials" -ForegroundColor White
    Write-Host "2. Re-run this installer to populate MCP config" -ForegroundColor White
    Write-Host "3. Restart Cursor to load the MCP server`n" -ForegroundColor White
}
Write-Host "Documentation: See MCP_SETUP.md for details`n" -ForegroundColor Gray
