
$ProjectRoot = "C:\Users\adesh\Documents\UrbanPulse"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Script = Join-Path $ProjectRoot "src\ingest.py"
$Log = Join-Path $ProjectRoot "logs\scheduled_ingest.log"

Set-Location $ProjectRoot

"===== $(Get-Date -Format o) | START =====" |
    Out-File -FilePath $Log -Append -Encoding utf8

$Output = & $Python $Script 2>&1
$ExitCode = $LASTEXITCODE

$Output |
    ForEach-Object { "$_" } |
    Out-File -FilePath $Log -Append -Encoding utf8

"===== $(Get-Date -Format o) | EXIT CODE: $ExitCode =====" |
    Out-File -FilePath $Log -Append -Encoding utf8

exit $ExitCode
