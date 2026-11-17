[CmdletBinding()]
param([string] $OutputDirectory = $PSScriptRoot)

$ErrorActionPreference = "Stop"
$framework = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319"
$compiler = Join-Path $framework "csc.exe"
$wpf = Join-Path $framework "WPF"
if (-not (Test-Path -LiteralPath $compiler)) { throw "Missing .NET Framework compiler: $compiler" }
$null = New-Item -ItemType Directory -Force -Path $OutputDirectory
$output = Join-Path $OutputDirectory "remote-helper.exe"
& $compiler /nologo /target:winexe /optimize /r:System.Web.Extensions.dll `
  "/r:$wpf\UIAutomationClient.dll" "/r:$wpf\UIAutomationTypes.dll" "/r:$wpf\WindowsBase.dll" `
  "/out:$output" (Join-Path $PSScriptRoot "remote-helper.cs")
if ($LASTEXITCODE -ne 0) { throw "remote-helper compilation failed: $LASTEXITCODE" }
Write-Host "Built $output"
