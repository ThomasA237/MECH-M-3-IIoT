
# Automatisierte HTTP-API-Tests fuer den Raspberry Pi Pico W
# Startet Smoke-Tests und Schemathesis

param(
    [string]$PicoIP = "192.168.0.79",
    [switch]$SkipCoverage
)

# Pfade bestimmen
$RepoPath = Split-Path -Parent $PSScriptRoot
$OpenAPI = Join-Path $RepoPath "docs\iot-specs\openapi.yaml"
$SmokeTest = Join-Path $PSScriptRoot "smoke_api.py"

# URL des Pico
$BaseURL = "http://$PicoIP"

# Pruefen, ob die Testdateien vorhanden sind
if (-not (Test-Path $OpenAPI)) {
    Write-Error "openapi.yaml nicht gefunden!"
    exit 1
}

if (-not (Test-Path $SmokeTest)) {
    Write-Error "smoke_api.py nicht gefunden!"
    exit 1
}

# Zum Repository-Hauptverzeichnis wechseln
Push-Location $RepoPath

try {
    # TEST 1: Eigene Python-Funktionstests
    Write-Host "`n[1/3] Starte HTTP-Smoke-Tests..." -ForegroundColor Cyan

    python $SmokeTest --url $BaseURL

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Smoke-Tests fehlgeschlagen!" -ForegroundColor Red
        exit 1
    }

    # TEST 2: Schemathesis Examples
    Write-Host "`n[2/3] Starte Schemathesis Examples..." -ForegroundColor Cyan

    schemathesis run $OpenAPI `
        --url $BaseURL `
        --workers 1 `
        --phases examples `
        --request-timeout 10 `
        --max-failures 3

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Examples-Test fehlgeschlagen!" -ForegroundColor Red
        exit 1
    }

    # TEST 3: Schemathesis Coverage
    if (-not $SkipCoverage) {
        Write-Host "`n[3/3] Starte Schemathesis Coverage..." -ForegroundColor Cyan

        schemathesis run $OpenAPI `
            --url $BaseURL `
            --workers 1 `
            --phases coverage `
            --request-timeout 10 `
            --max-failures 3

        if ($LASTEXITCODE -ne 0) {
            Write-Host "Coverage-Test fehlgeschlagen!" -ForegroundColor Red
            exit 1
        }
    }
    else {
        Write-Host "`n[3/3] Coverage uebersprungen." -ForegroundColor Yellow
    }

    Write-Host "`nAlle ausgefuehrten Tests erfolgreich!" -ForegroundColor Green
}
finally {
    # Urspruengliches Arbeitsverzeichnis wiederherstellen
    Pop-Location
}
