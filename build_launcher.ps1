$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Compilateur .NET Framework csc.exe introuvable.' }
$build = Join-Path $root 'build\launcher'
New-Item -ItemType Directory -Force -Path $build | Out-Null
$target = Join-Path $build 'Atelier Images.exe'
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu /reference:System.Windows.Forms.dll "/out:$target" (Join-Path $root 'atelier_images\launcher\Launcher.cs')
if ($LASTEXITCODE -ne 0) { throw 'La compilation du lanceur a echoue.' }
Copy-Item -LiteralPath $target -Destination (Join-Path $root 'Atelier Images.exe') -Force
Write-Host "Executable cree : $(Join-Path $root 'Atelier Images.exe')"
