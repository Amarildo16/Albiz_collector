$ErrorActionPreference = "Stop"

if ($PSScriptRoot) {
    Set-Location $PSScriptRoot
}

$python = ".\.venv\Scripts\python.exe"
$limit = 1000
$delaySeconds = 1.5
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "reports\opencorporates_continue_$stamp.log"
$batch = 1

New-Item -ItemType Directory -Force reports | Out-Null

function Write-LogLine {
    param([string]$Message)

    $Message | Tee-Object -FilePath $log -Append
}

function Write-LogOutput {
    param([object[]]$Output)

    $Output |
        ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            }
            else {
                $_.ToString()
            }
        } |
        Tee-Object -FilePath $log -Append
}

function Invoke-AlbizCommand {
    param([string[]]$Arguments)

    # httpx writes INFO logs to stderr. We capture them, but we do not want
    # PowerShell to treat those log lines as fatal errors.
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        $output = & $python @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    $cleanOutput = $output | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.Exception.Message
        }
        else {
            $_.ToString()
        }
    }

    return [PSCustomObject]@{
        Output = $cleanOutput
        Text = ($cleanOutput -join [Environment]::NewLine)
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
Write-LogLine "limit=$limit delaySeconds=$delaySeconds force=false"

while ($true) {
    Write-LogLine ""
    Write-LogLine "===== DRY RUN $batch START $(Get-Date) ====="

    $dryResult = Invoke-AlbizCommand @(
        "-m", "albiz_collector.cli",
        "run", "opencorporates-financials",
        "--limit", "$limit",
        "--dry-run"
    )

    if ($dryResult.ExitCode -ne 0) {
        Write-LogOutput $dryResult.Output
        Write-LogLine "===== DRY RUN $batch FAILED exit=$($dryResult.ExitCode) $(Get-Date) ====="
        exit $dryResult.ExitCode
    }

    try {
        $drySummary = Get-JsonSummary $dryResult.Text
    }
    catch {
        Write-LogOutput $dryResult.Output
        Write-LogLine "===== DRY RUN $batch FAILED invalid-json $(Get-Date) ====="
        $_ | Out-String | Tee-Object -FilePath $log -Append
        exit 1
    }

    $selectedCount = [int]$drySummary.selected_nipt_count
    $skippedRecent = [int]$drySummary.skipped_recent

    Write-LogLine "DRY RUN $batch summary: selected_nipt_count=$selectedCount skipped_recent=$skippedRecent http_requests_executed=$($drySummary.http_requests_executed)"

    if ($selectedCount -eq 0) {
        Write-LogLine "===== COMPLETE: no eligible NIPTs remain $(Get-Date) ====="
        break
    }

    Write-LogLine "===== BATCH $batch START selected=$selectedCount $(Get-Date) ====="

    $batchResult = Invoke-AlbizCommand @(
        "-m", "albiz_collector.cli",
        "run", "opencorporates-financials",
        "--limit", "$limit",
        "--delay-seconds", "$delaySeconds"
    )

    Write-LogOutput $batchResult.Output

    if ($batchResult.ExitCode -ne 0) {
        Write-LogLine "===== BATCH $batch FAILED exit=$($batchResult.ExitCode) $(Get-Date) ====="
        exit $batchResult.ExitCode
    }

    try {
        $batchSummary = Get-JsonSummary $batchResult.Text
    }
    catch {
        Write-LogLine "===== BATCH $batch FAILED invalid-json-summary $(Get-Date) ====="
        $_ | Out-String | Tee-Object -FilePath $log -Append
        exit 1
    }

    $parseErrors = [int]$batchSummary.parse_errors
    $httpErrors = [int]$batchSummary.http_errors
    $persistenceErrors = [int]$batchSummary.persistence_errors

    Write-LogLine "BATCH $batch summary: selected=$($batchSummary.selected_nipt_count) requests=$($batchSummary.http_requests_executed) pages_found=$($batchSummary.pages_found) pages_missing=$($batchSummary.pages_missing) no_financial_or_with_financial=$($batchSummary.companies_with_financial_data) rows=$($batchSummary.financial_rows_upserted) parse_errors=$parseErrors http_errors=$httpErrors persistence_errors=$persistenceErrors"

    if (($parseErrors -gt 0) -or ($httpErrors -gt 0) -or ($persistenceErrors -gt 0)) {
        Write-LogLine "===== BATCH $batch STOPPED because errors were reported $(Get-Date) ====="
        Write-LogLine "Review the log before continuing. Do not use --force."
        exit 2
    }

    Write-LogLine "===== BATCH $batch END $(Get-Date) ====="

    $batch++
}

Write-LogLine "===== OPENCORPORATES CONTINUE END $(Get-Date) ====="