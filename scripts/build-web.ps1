# Сборка веб-версии под Windows: аналог `make export-web assemble`.
#   powershell -ExecutionPolicy Bypass -File scripts\build-web.ps1 [-Godot <путь к exe>] [-SkipExport]
# Результат: dist/web (Godot-экспорт + аудио-движок из web/). Раздаёт его бэкенд (StaticFiles на /).
param(
    [string]$Godot = $env:GODOT,
    [switch]$SkipExport
)
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Project = Join-Path $Root 'godot\karaoke-jam'
$Web = Join-Path $Root 'web'
$Dist = Join-Path $Root 'dist\web'

function Find-Godot {
    if ($Godot -and (Test-Path $Godot)) { return $Godot }
    $settings = Join-Path $Root '.vscode\settings.json'
    if (Test-Path $settings) {
        $p = (Get-Content $settings -Raw | ConvertFrom-Json).'godotTools.editorPath.godot4'
        if ($p -and (Test-Path $p)) { return $p }
    }
    $cmd = Get-Command godot*, Godot* -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { return $cmd.Source }
    throw 'Godot не найден: передайте -Godot <путь к exe> или задайте $env:GODOT.'
}

New-Item -ItemType Directory -Force -Path $Dist | Out-Null

if (-not $SkipExport) {
    $exe = Find-Godot
    Write-Host "== Экспорт Godot ($exe)"
    # путь экспорта — относительно папки проекта (как export_path в export_presets.cfg)
    & $exe --headless --path $Project --export-release 'Web' '../../dist/web/index.html' | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Экспорт Godot завершился с кодом $LASTEXITCODE" }
    if (-not (Test-Path (Join-Path $Dist 'index.pck'))) {
        throw 'После экспорта нет dist/web/index.pck — проверьте шаблоны экспорта Web для этой версии Godot.'
    }
}

Write-Host '== Копирование аудио-движка из web/'
robocopy $Web $Dist /E /NFL /NDL /NJH /NJS /NP `
    /XD node_modules test `
    /XF package.json package-lock.json | Out-Host
# robocopy: коды 0–7 — успех, 8+ — ошибка
if ($LASTEXITCODE -ge 8) { throw "robocopy завершился с кодом $LASTEXITCODE" }
$global:LASTEXITCODE = 0

$missing = @('index.html', 'config.js', 'voice.js', 'vendor\pitchy.bundle.js') |
    Where-Object { -not (Test-Path (Join-Path $Dist $_)) }
if ($missing) {
    Write-Warning ("В dist/web нет: " + ($missing -join ', '))
    if ($missing -contains 'vendor\pitchy.bundle.js') {
        Write-Warning 'Живой микрофон не заработает (работает только ?mock=...). Соберите: cd web; npm install; npm run vendor'
    }
} else {
    Write-Host '== Готово: dist/web собран полностью'
}
Write-Host 'Запуск: cd backend; uv run uvicorn app.main:app --port 8000  ->  http://localhost:8000/?mock=perfect'
