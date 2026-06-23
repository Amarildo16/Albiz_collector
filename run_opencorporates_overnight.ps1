$ErrorActionPreference = "Stop"

if ($PSScriptRoot) {
    Set-Location $PSScriptRoot
}

$python = ".\.venv\Scripts\python.exe"
$limit = 1000
$delaySeconds = 2.5
$maxHttpErrorsPerBatch = 50

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "reports\opencorporates_continue_$stamp.log"
$batch = 1

New-Item -ItemType Directory -Force reports | Out-Null

function Write-LogLine {
    param([string]$Message)
    $Message | Tee-Object -FilePath $log -Append
}

function Invoke-AlbizLiveCommand {
    param(
        [string[]]$Arguments,
        [string]$TempLog
    )

    if (Test-Path $TempLog) {
        Remove-Item $TempLog -Force
    }

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        & $python @Arguments 2>&1 |
            ForEach-Object {
                if ($_ -is [System.Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                }
                else {
                    $_.ToString()
                }
            } |
            Tee-Object -FilePath $TempLog |
            Tee-Object -FilePath $log -Append

        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    $text = ""
    if (Test-Path $TempLog) {
        $text = Get-Content $TempLog -Raw
    }

    return [PSCustomObject]@{
        Text = $text
        ExitCode = $exitCode
    }
}

function Get-JsonSummary {
    param([string]$Text)

    $jsonStart = $Text.IndexOf("{")

    if ($jsonStart -lt 0) {
        throw "Missing JSON summary in command output."
    }

    return $Text.Substring($jsonStart) | ConvertFrom-Json
}

Write-LogLine "===== OPENCORPORATES CONTINUE START $(Get-Date) ====="
Write-LogLine "limit=$limit delaySeconds=$delaySeconds force=false dry_run=false maxHttpErrorsPerBatch=$maxHttpErrorsPerBatch"

while ($true) {
    Write-LogLine ""
    Write-LogLine "===== BATCH $batch START $(Get-Date) ====="

    $tempLog = "reports\opencorporates_batch_${stamp}_${batch}.tmp.log"

    $batchResult = Invoke-AlbizLiveCommand `
        -Arguments @(
            "-m", "albiz_collector.cli",
            "run", "opencorporates-financials",
            "--limit", "$limit",
            "--delay-seconds", "$delaySeconds"
        ) `
        -TempLog $tempLog

    if ($batchResult.ExitCode -ne 0) {
        Write-LogLine "===== BATCH $batch FAILED exit=$($batchResult.ExitCode) $(Get-Date) ====="
        Write-LogLine "Review the log before continuing. Do not use --force."
        exit $batchResult.ExitCode
    }

    try {
        $summary = Get-JsonSummary $batchResult.Text
    }
    catch {
        Write-LogLine "===== BATCH $batch FAILED invalid-json-summary $(Get-Date) ====="
        $_ | Out-String | Tee-Object -FilePath $log -Append
        exit 1
    }

    $selectedCount = [int]$summary.selected_nipt_count
    $requestsExecuted = [int]$summary.http_requests_executed
    $pagesFound = [int]$summary.pages_found
    $pagesMissing = [int]$summary.pages_missing
    $companiesWithFinancialData = [int]$summary.companies_with_financial_data
    $rowsUpserted = [int]$summary.financial_rows_upserted
    $parseErrors = [int]$summary.parse_errors
    $httpErrors = [int]$summary.http_errors
    $persistenceErrors = [int]$summary.persistence_errors
    $skippedRecent = [int]$summary.skipped_recent

    Write-LogLine "BATCH $batch summary: selected=$selectedCount skipped_recent=$skippedRecent requests=$requestsExecuted pages_found=$pagesFound pages_missing=$pagesMissing companies_with_financial_data=$companiesWithFinancialData rows=$rowsUpserted parse_errors=$parseErrors http_errors=$httpErrors persistence_errors=$persistenceErrors"

    if ($selectedCount -eq 0) {
        Write-LogLine "===== COMPLETE: no eligible NIPTs remain $(Get-Date) ====="
        break
    }

    if (($parseErrors -gt 0) -or ($persistenceErrors -gt 0)) {
        Write-LogLine "===== BATCH $batch STOPPED because parse/persistence errors were reported $(Get-Date) ====="
        Write-LogLine "Review the log before continuing. Do not use --force."
        exit 2
    }

    if ($httpErrors -gt $maxHttpErrorsPerBatch) {
        Write-LogLine "===== BATCH $batch STOPPED because too many HTTP errors were reported: $httpErrors $(Get-Date) ====="
        Write-LogLine "Likely server/rate-limit/network issue. Review the log before continuing. Do not use --force."
        exit 2
    }

    if ($httpErrors -gt 0) {
        Write-LogLine "===== BATCH $batch WARNING: http_errors=$httpErrors; keeping them retryable and continuing $(Get-Date) ====="
    }

    Write-LogLine "===== BATCH $batch END $(Get-Date) ====="

    $batch++
}

Write-LogLine "===== OPENCORPORATES CONTINUE END $(Get-Date) ====="
