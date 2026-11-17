[CmdletBinding()]
param([string] $InnoCompilerPath = "")

$ErrorActionPreference = "Stop"
$Project = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$Repository = Split-Path -Parent $Project
$BuildPython = Join-Path $Project ".venv\Scripts\python.exe"
$Dist = Join-Path $Repository "dist"
$Package = Join-Path $Dist "XiaomiRemoteAgent"
$Work = Join-Path $Project "build\pyinstaller"
$env:PYINSTALLER_CONFIG_DIR = Join-Path $Project "build\pyinstaller-cache"
$env:PYTHONIOENCODING = "utf-8"

function Reset-SafeDirectory([string] $Path) {
  $target = [IO.Path]::GetFullPath($Path)
  $allowed = [IO.Path]::GetFullPath($Repository).TrimEnd('\') + '\'
  if (-not $target.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to clean outside repository: $target"
  }
  if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
  $null = New-Item -ItemType Directory -Force -Path $target
}

if (-not (Test-Path -LiteralPath $BuildPython)) { throw "Missing app\.venv\Scripts\python.exe" }
$gadget = Join-Path $Project "source\bridges\xiaomi\assets\frida-gadget-17.15.3-windows-x86_64.dll.xz"
if (-not (Test-Path -LiteralPath $gadget)) { throw "Missing local Frida Gadget; this build is offline." }
if ((Get-FileHash -LiteralPath $gadget -Algorithm SHA256).Hash -ne
    'B566D70189B6D551AD8F4E0BEA24DE08A3D4C0F559BB35B2BDB67D45182240C2') {
  throw "Frida Gadget SHA-256 mismatch"
}
$fridaLicense = Join-Path $Project "licenses\frida-COPYING.txt"
if (-not (Test-Path -LiteralPath $fridaLicense)) { throw "Missing Frida license" }

& $BuildPython (Join-Path $Project "scripts\generate-icon.py")
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed" }
Reset-SafeDirectory $Package
$null = New-Item -ItemType Directory -Force -Path $Work
& $BuildPython -m PyInstaller --noconfirm --clean --distpath $Dist --workpath $Work `
  (Join-Path $Project "source\XiaomiRemoteAgent.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed: $LASTEXITCODE" }

& (Join-Path $Project "helper\build-helper.ps1") -OutputDirectory $Package
$support = Join-Path $Package "support"
$licenses = Join-Path $Package "licenses"
$null = New-Item -ItemType Directory -Force -Path $support, $licenses
Copy-Item -LiteralPath (Join-Path $Project "LICENSE") -Destination (Join-Path $Package "LICENSE")
Copy-Item -LiteralPath (Join-Path $Repository "README.md") -Destination (Join-Path $Package "README.md")
Copy-Item -LiteralPath (Join-Path $Project "THIRD_PARTY_NOTICES.md") -Destination $Package
Copy-Item -LiteralPath $fridaLicense -Destination $licenses
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "standalone\setup\configure-xiaomi-audio.ps1") -Destination $support
& $BuildPython (Join-Path $Project "scripts\collect-licenses.py") $licenses
if ($LASTEXITCODE -ne 0) { throw "Dependency license collection failed" }

$exe = Join-Path $Package "XiaomiRemoteAgent.exe"
foreach ($required in @($exe, (Join-Path $Package "remote-helper.exe"), (Join-Path $Package "LICENSE"))) {
  if (-not (Test-Path -LiteralPath $required)) { throw "Missing package file: $required" }
}
$packagedGadget = @(Get-ChildItem -LiteralPath $Package -Recurse -File -Filter "frida-gadget-*.dll.xz")
if ($packagedGadget.Count -ne 1 -or
    (Get-FileHash -LiteralPath $packagedGadget[0].FullName -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath $gadget -Algorithm SHA256).Hash) { throw "Packaged Frida Gadget check failed" }

$archiveListing = (& $BuildPython -m PyInstaller.utils.cliutils.archive_viewer -r -b $exe) -join "`n"
if ($LASTEXITCODE -ne 0) { throw "Cannot inspect packaged executable" }
foreach ($module in @('winrt.windows.foundation', 'winrt.windows.foundation.collections',
    'bridges.xiaomi.hid_tap_injector', 'standalone.default_microphone')) {
  if ($archiveListing -notmatch [regex]::Escape($module)) { throw "Missing packaged module: $module" }
}
if ($archiveListing -match 'bridges\.(t1|hanvon)|standalone\.windows_update') {
  throw "Unexpected removed module in package"
}
[IO.File]::WriteAllText((Join-Path $Project "build\package-archive.txt"), $archiveListing, [Text.UTF8Encoding]::new($false))

$innoCandidates = @($InnoCompilerPath, "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
$command = Get-Command "ISCC.exe" -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if ($command) { $innoCandidates += $command.Source }
$InnoCompiler = $innoCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if ($InnoCompiler) {
  $sourceText = Get-Content -LiteralPath (Join-Path $Project "source\standalone\xiaomi_main.py") -Raw -Encoding UTF8
  $version = [regex]::Match($sourceText, 'APP_VERSION\s*=\s*"([^"]+)"').Groups[1].Value
  $setupOutput = Join-Path $Dist "installer"
  $null = New-Item -ItemType Directory -Force -Path $setupOutput
  & $InnoCompiler "/DAppVersion=$version" "/DVersionInfoVersion=$version.0" "/DSourceDir=$Package" "/DOutputDir=$setupOutput" `
    (Join-Path $PSScriptRoot "standalone\setup\XiaomiRemoteAgentSetup.iss")
  if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed: $LASTEXITCODE" }
} else {
  Write-Host "ISCC not found; skipping installer. Folder package is ready."
}
Write-Host "BUILD OK: $Package"
Get-Item -LiteralPath $exe, (Join-Path $Package "remote-helper.exe") | Select-Object Name, Length
