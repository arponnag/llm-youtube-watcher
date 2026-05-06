param(
    [string]$DeepSeekApiKey = "sk-a3a23b88b92b4390b8927579c544b5ca",
    [string]$DeepSeekModel = "deepseek-v4-flash",
    [string]$DeepSeekBaseUrl = "https://api.deepseek.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".\.venv\Scripts\Activate.ps1")) {
    Write-Error "Virtual environment not found at .\.venv. Create it first: python -m venv .venv"
}

if ([string]::IsNullOrWhiteSpace($DeepSeekApiKey)) {
    $DeepSeekApiKey = Read-Host "Enter DEEPSEEK_API_KEY"
}

if ([string]::IsNullOrWhiteSpace($DeepSeekApiKey)) {
    Write-Error "DEEPSEEK_API_KEY is required."
}

. .\.venv\Scripts\Activate.ps1

$env:DEEPSEEK_API_KEY = $DeepSeekApiKey
$env:DEEPSEEK_MODEL = $DeepSeekModel
$env:DEEPSEEK_BASE_URL = $DeepSeekBaseUrl

# Optional strict quality gates for local validation.
$env:FAIL_ON_LOW_TRANSCRIPT_COVERAGE = "0"
$env:MIN_TRANSCRIPT_COVERAGE = "0.6"
$env:MIN_TRANSCRIPT_CHARS = "120"
# Keep API usage predictable for local runs.
$env:MAX_TOTAL_VIDEOS = "10"

python -m pip install -r requirements.txt
python src/pipeline.py
python src/build_site.py

Write-Host ""
Write-Host "Local run completed."
Write-Host "Check: data/videos.json -> quality_metrics"
Write-Host "Open:  site/index.html"
