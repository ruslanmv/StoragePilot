# StoragePilot Setup Script for Windows PowerShell
# =================================================
# Usage:
#   .\setup.ps1           - Full installation + optional wizard
#   .\setup.ps1 -Wizard   - Run only the interactive setup wizard
#   .\setup.ps1 -Install  - Run only the installation (no wizard)

param(
    [switch]$Wizard,
    [switch]$Install,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# Show help
if ($Help) {
    Write-Host "StoragePilot Setup Script for Windows" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Usage: .\setup.ps1 [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Wizard   Run only the interactive setup wizard"
    Write-Host "  -Install  Run only the installation (no wizard)"
    Write-Host "  -Help     Show this help message"
    Write-Host ""
    Write-Host "Default: Runs installation, then optionally the wizard"
    exit 0
}

# Determine what to run
$RunInstall = -not $Wizard
$RunWizard = $Wizard

# Change to script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

function Write-Banner {
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Cyan
    Write-Host "           StoragePilot Installation Script                       " -ForegroundColor Cyan
    Write-Host "       AI-Powered Storage Lifecycle Manager                       " -ForegroundColor Cyan
    Write-Host "==================================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-PythonVersion {
    try {
        $pythonVersion = & python --version 2>&1
        if ($pythonVersion -match "Python (\d+\.\d+)") {
            $version = [version]$Matches[1]
            if ($version -ge [version]"3.9") {
                Write-Host "   Found $pythonVersion" -ForegroundColor Green
                return $true
            }
        }
        Write-Host "   Python 3.9+ required, found: $pythonVersion" -ForegroundColor Red
        return $false
    }
    catch {
        Write-Host "   Python not found. Please install Python 3.9+" -ForegroundColor Red
        Write-Host "   Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
        return $false
    }
}

function Install-VirtualEnv {
    Write-Host ""
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow

    if (Test-Path ".venv") {
        Write-Host "   Virtual environment already exists" -ForegroundColor Green
    }
    else {
        & python -m venv .venv
        Write-Host "   Virtual environment created" -ForegroundColor Green
    }

    # Activate virtual environment
    $activateScript = ".\.venv\Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        & $activateScript
        Write-Host "   Virtual environment activated" -ForegroundColor Green
    }
    else {
        Write-Host "   Failed to activate virtual environment" -ForegroundColor Red
        exit 1
    }
}

function Install-Dependencies {
    Write-Host ""
    Write-Host "Upgrading pip..." -ForegroundColor Yellow
    & python -m pip install --upgrade pip -q

    Write-Host ""
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    & pip install -r requirements.txt -q
    Write-Host "   Dependencies installed" -ForegroundColor Green
}

function New-Directories {
    Write-Host ""
    Write-Host "Creating directories..." -ForegroundColor Yellow

    @("logs", "config") | ForEach-Object {
        if (-not (Test-Path $_)) {
            New-Item -ItemType Directory -Path $_ -Force | Out-Null
        }
    }
    Write-Host "   Directories created" -ForegroundColor Green
}

function Test-ApiKeys {
    Write-Host ""
    Write-Host "Checking API keys..." -ForegroundColor Yellow

    $hasKey = $false

    if ($env:OPENAI_API_KEY) {
        Write-Host "   OPENAI_API_KEY found" -ForegroundColor Green
        $hasKey = $true
    }
    if ($env:ANTHROPIC_API_KEY) {
        Write-Host "   ANTHROPIC_API_KEY found" -ForegroundColor Green
        $hasKey = $true
    }

    if (-not $hasKey) {
        Write-Host "   No API key found (Ollama will be used by default)" -ForegroundColor Yellow
    }
}

function Show-Completion {
    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host "                 Installation Complete!                           " -ForegroundColor Green
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host ""
}

function Invoke-SetupWizard {
    Write-Host ""
    Write-Host "Starting interactive setup wizard..." -ForegroundColor Cyan
    Write-Host ""

    # Activate venv if exists
    $activateScript = ".\.venv\Scripts\Activate.ps1"
    if (Test-Path $activateScript) {
        & $activateScript
    }

    & python scripts\setup_wizard.py
}

function Show-QuickStart {
    Write-Host ""
    Write-Host "Quick Start:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   1. Activate the virtual environment:" -ForegroundColor White
    Write-Host "      .\.venv\Scripts\Activate.ps1" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   2. Run the setup wizard to configure LLM and paths:" -ForegroundColor White
    Write-Host "      python scripts\setup_wizard.py" -ForegroundColor Gray
    Write-Host ""
    Write-Host "   3. Run StoragePilot:" -ForegroundColor White
    Write-Host "      python main.py --dry-run    # CLI (preview mode)" -ForegroundColor Gray
    Write-Host "      python main.py --ui         # Web dashboard" -ForegroundColor Gray
    Write-Host ""
    Write-Host "For more information, see README.md" -ForegroundColor Yellow
    Write-Host ""
}

# Main execution
if ($RunInstall) {
    Write-Banner

    Write-Host "Checking Python version..." -ForegroundColor Yellow
    if (-not (Test-PythonVersion)) {
        exit 1
    }

    Install-VirtualEnv
    Install-Dependencies
    New-Directories
    Test-ApiKeys
    Show-Completion

    # Ask to run wizard
    if (-not $RunWizard) {
        $response = Read-Host "Would you like to run the interactive setup wizard? (y/N)"
        if ($response -match "^[Yy]") {
            $RunWizard = $true
        }
    }
}

if ($RunWizard) {
    Invoke-SetupWizard
}
else {
    Show-QuickStart
}
