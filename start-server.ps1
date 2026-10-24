# Start de lokale xiaozhi-server (Claude + Whisper + Edge-stemmen) voor het bord.
# Sleutels komen uit de omgevingsvariabelen ANTHROPIC_API_KEY en OPENAI_API_KEY
# (eenmalig instellen met setx, zie README in deze map).

$root = $PSScriptRoot
$venv = Join-Path $root '.venv'

# Gebruikersvariabelen opnieuw inlezen, zodat net met setx gezette sleutels meetellen.
foreach ($name in 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY') {
    $value = [Environment]::GetEnvironmentVariable($name, 'User')
    if ($value) { Set-Item -Path "Env:$name" -Value $value }
    if (-not (Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue)) {
        Write-Warning "$name is niet ingesteld."
    }
}

# opus.dll (uit PyOgg) en ffmpeg (winget, Gyan.FFmpeg) vindbaar maken.
$ffmpeg = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages') -Filter 'Gyan.FFmpeg*' -ErrorAction SilentlyContinue |
    ForEach-Object { Get-ChildItem $_.FullName -Recurse -Filter ffmpeg.exe } | Select-Object -First 1
if ($ffmpeg) { $env:PATH = $ffmpeg.DirectoryName + ';' + $env:PATH } else { Write-Warning 'ffmpeg niet gevonden.' }
$env:PATH = (Join-Path $venv 'Lib\site-packages\pyogg') + ';' + $env:PATH

Set-Location (Join-Path $root 'main\xiaozhi-server')
& (Join-Path $venv 'Scripts\python.exe') app.py
