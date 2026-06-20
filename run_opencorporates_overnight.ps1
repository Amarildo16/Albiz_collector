$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = ".\.venv\Scripts\python.exe"
$limit = 1000
$delaySeconds = 1.5
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = "reports\opencorporates_overnight_$stamp.log"
$batch = 1

New-Item -ItemType Directory -Force reports | Out-Null

function Write-LogOutput {
    param([object[]]$Output)

    $Output | ForEach-Object { $_.ToString() } | Tee-Object -FilePath $log -Append
}

while ($true) {
    "===== DRY RUN $batch START $(Get-Date) =====" | Tee-Object -FilePath $log -Append
    $dryOutput = & $python -m albiz_collector.cli run opencorporates-financials --limit $limit --dry-run 2>&1
    $dryExitCode = $LASTEXITCODE
    Write-LogOutput $dryOutput

    if ($dryExitCode -ne 0) {
        "===== DRY RUN $batch FAILED (exit $dryExitCode) $(Get-Date) =====" | Tee-Object -FilePath $log -Append
        exit $dryExitCode
    }

    $dryText = ($dryOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    $jsonStart = $dryText.IndexOf("{")
    if ($jsonStart -lt 0) {
        "===== DRY RUN $batch FAILED (missing JSON summary) $(Get-Date) =====" | Tee-Object -FilePath $log -Append
        exit 1
    }

    try {
        $drySummary = $dryText.Substring($jsonStart) | ConvertFrom-Json
        $selectedCount = [int]$drySummary.selected_nipt_count
    }
    catch {
        "===== DRY RUN $batch FAILED (invalid JSON summary) $(Get-Date) =====" | Tee-Object -FilePath $log -Append
        $_ | Out-String | Tee-Object -FilePath $log -Append
        exit 1
    }

    if ($selectedCount -eq 0) {
        "===== COMPLETE: no eligible NIPTs remain $(Get-Date) =====" | Tee-Object -FilePath $log -Append
        break
    }

    "===== BATCH $batch START selected=$selectedCount $(Get-Date) =====" | Tee-Object -FilePath $log -Append
    $batchOutput = & $python -m albiz_collector.cli run opencorporates-financials --limit $limit --delay-seconds $delaySeconds 2>&1
    $batchExitCode = $LASTEXITCODE
    Write-LogOutput $batchOutput

    if ($batchExitCode -ne 0) {
        "===== BATCH $batch FAILED (exit $batchExitCode) $(Get-Date) =====" | Tee-Object -FilePath $log -Append
        exit $batchExitCode
    }

    "===== BATCH $batch END $(Get-Date) =====" | Tee-Object -FilePath $log -Append
    $batch++
}
