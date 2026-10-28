# Starts the dashboard on the LightGBM v2 model:
#   run_model.py --model lightgbm --extra ratios activity patterns --dashboard
# Opens the FastAPI backend (:8000) and the Next.js dashboard (:3000) in two new windows.
$root = $PSScriptRoot
$py = "F:\ana\envs\xrpl_env\python.exe"
$v2 = "$root\outputs\models\lightgbm_activity_patterns_ratios"

# the API still loads the dataset tables on start-up; build them once if missing
if (-not (Test-Path "$root\data\processed\official\scores.parquet")) {
    Write-Host "Preparing dataset tables (one time)..."
    Push-Location "$root\src"
    & $py import_official.py; & $py features.py; & $py train.py; & $py predict.py; & $py detect.py
    Pop-Location
}

# the v2 model results the dashboard shows; build them if missing (about 2-5 minutes)
if (-not (Test-Path "$v2\evaluation.json") -or -not (Test-Path "$v2\train_scores.parquet")) {
    Write-Host "Running the v2 LightGBM model for the dashboard..."
    Push-Location "$root\src"
    & $py run_model.py --model lightgbm --extra ratios activity patterns --dashboard
    Pop-Location
}

if (-not (Test-Path "$root\frontend\node_modules")) {
    Push-Location "$root\frontend"; npm install; Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; `$env:TXMODEL_RUN='lightgbm_activity_patterns_ratios'; & '$py' -m uvicorn api.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Write-Host "API:       http://127.0.0.1:8000/docs"
Write-Host "Dashboard: http://localhost:3000   (LightGBM v2 model)"
