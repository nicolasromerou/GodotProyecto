param([string]$GodotPath = $env:GODOT_PATH)
$ErrorActionPreference = 'Stop'
if (-not $GodotPath) {
    $GodotPath = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Godot_v4.7.2-stable_win64.exe'
}
if (-not (Test-Path -LiteralPath $GodotPath -PathType Leaf)) {
    throw 'Indica el ejecutable principal: .\abrir-godot.ps1 -GodotPath "C:\ruta\Godot.exe"'
}
& $GodotPath --editor --path $PSScriptRoot
