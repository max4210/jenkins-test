#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Build (or destroy) the CML lab locally using Terraform — no Jenkins needed.

.DESCRIPTION
    Reads credentials from .env, runs nac-validate, then terraform init/plan/apply.
    Pass -Destroy to tear down the lab instead.

.EXAMPLE
    .\deploy-local.ps1              # validate + create/update lab
    .\deploy-local.ps1 -Destroy     # destroy the lab
    .\deploy-local.ps1 -SkipValidation  # skip nac-validate, go straight to Terraform
#>

param(
    [switch]$Destroy,
    [switch]$SkipValidation,
    [switch]$PlanOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# ── Load .env ────────────────────────────────────────────────────
$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    Write-Host "[*] Loading credentials from .env" -ForegroundColor Cyan
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $key, $val = $line -split "=", 2
            $key = $key.Trim()
            $val = $val.Trim()
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
} else {
    Write-Host "[!] No .env file found at $envFile" -ForegroundColor Yellow
    Write-Host "    Create one with CML_USERNAME, CML_PASSWORD, CML_URL" -ForegroundColor Yellow
}

$cmlUser = $env:CML_USERNAME
$cmlPass = $env:CML_PASSWORD
$cmlUrl  = $env:CML_URL
if (-not $cmlUrl.StartsWith("http")) { $cmlUrl = "https://$cmlUrl" }

$deviceUser = if ($env:DEVICE_USERNAME) { $env:DEVICE_USERNAME } else { $cmlUser }
$devicePass = if ($env:DEVICE_PASSWORD) { $env:DEVICE_PASSWORD } else { $cmlPass }

if (-not $cmlUser -or -not $cmlPass) {
    Write-Host "[!] CML_USERNAME and CML_PASSWORD must be set in .env or environment" -ForegroundColor Red
    exit 1
}

Write-Host "[*] CML URL:  $cmlUrl" -ForegroundColor Cyan
Write-Host "[*] CML User: $cmlUser" -ForegroundColor Cyan
Write-Host ""

# ── Validate YAML ────────────────────────────────────────────────
if (-not $Destroy -and -not $SkipValidation) {
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host "  Stage: Validate YAML data" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green

    $nacValidate = Get-Command nac-validate -ErrorAction SilentlyContinue
    if ($nacValidate) {
        Write-Host "[*] Running schema + rules validation..." -ForegroundColor Cyan
        & nac-validate -s (Join-Path $projectRoot ".schema.yaml") -r (Join-Path $projectRoot ".rules") (Join-Path $projectRoot "data/")
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] Validation FAILED — fix errors above before deploying." -ForegroundColor Red
            exit 1
        }
        Write-Host "[+] Validation passed." -ForegroundColor Green
    } else {
        Write-Host "[!] nac-validate not found — skipping validation." -ForegroundColor Yellow
        Write-Host "    Install: pip install nac-validate" -ForegroundColor Yellow
    }

    $crossValidate = Join-Path $projectRoot "scripts/cross_validate.py"
    if (Test-Path $crossValidate) {
        Write-Host "[*] Running cross-file validation..." -ForegroundColor Cyan
        python $crossValidate
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[!] Cross-validation FAILED." -ForegroundColor Red
            exit 1
        }
        Write-Host "[+] Cross-validation passed." -ForegroundColor Green
    }
    Write-Host ""
}

# ── Terraform ────────────────────────────────────────────────────
$tfDir = Join-Path $projectRoot "terraform"

Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Stage: Terraform $(if ($Destroy) {'Destroy'} elseif ($PlanOnly) {'Plan'} else {'Apply'})" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green

# Set TF variables via environment
$env:TF_VAR_cml_url        = $cmlUrl
$env:TF_VAR_cml_username   = $cmlUser
$env:TF_VAR_cml_password   = $cmlPass
$env:TF_VAR_device_username = $deviceUser
$env:TF_VAR_device_password = $devicePass

Push-Location $tfDir
try {
    # Init
    Write-Host "[*] terraform init..." -ForegroundColor Cyan
    terraform init -input=false
    if ($LASTEXITCODE -ne 0) { throw "terraform init failed" }

    if ($Destroy) {
        Write-Host "[*] terraform destroy..." -ForegroundColor Cyan
        terraform destroy -input=false -auto-approve
        if ($LASTEXITCODE -ne 0) { throw "terraform destroy failed" }
        Write-Host "[+] Lab destroyed." -ForegroundColor Green
    }
    elseif ($PlanOnly) {
        Write-Host "[*] terraform plan..." -ForegroundColor Cyan
        terraform plan -input=false
        if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }
    }
    else {
        # Plan
        Write-Host "[*] terraform plan..." -ForegroundColor Cyan
        terraform plan -input=false -out=tfplan
        if ($LASTEXITCODE -ne 0) { throw "terraform plan failed" }

        # Apply
        Write-Host "[*] terraform apply..." -ForegroundColor Cyan
        terraform apply -input=false tfplan
        if ($LASTEXITCODE -ne 0) { throw "terraform apply failed" }
        Remove-Item -Path tfplan -ErrorAction SilentlyContinue

        Write-Host ""
        Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
        Write-Host "  Lab deployed successfully!" -ForegroundColor Green
        Write-Host "════════════════════════════════════════════════════════════" -ForegroundColor Green
        terraform output
    }
}
finally {
    Pop-Location
}
