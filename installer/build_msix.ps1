# 符卡作业簿 · 构建 MSIX 安装包（英文产物名）
# 依赖：Windows 10/11 SDK（makeappx.exe）、PyInstaller 产物 dist\SpellCardHomework\
# 用法：powershell -ExecutionPolicy Bypass -File installer\build_msix.ps1

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$dist = Join-Path $root "dist\SpellCardHomework"
$msixDir = Join-Path $PSScriptRoot "msix"
$build = Join-Path $msixDir "build"
$outDir = Join-Path $PSScriptRoot "Output"

if (-not (Test-Path (Join-Path $dist "SpellCardHomework.exe"))) {
    Write-Error "找不到 dist\SpellCardHomework\SpellCardHomework.exe，请先运行 PyInstaller 构建。"
}

if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory $build | Out-Null
Copy-Item "$dist\*" $build -Recurse

Copy-Item (Join-Path $msixDir "AppxManifest.xml") $build
if (-not (Test-Path (Join-Path $msixDir "Assets"))) {
    python (Join-Path $msixDir "make_logos.py")
}
Copy-Item (Join-Path $msixDir "Assets") $build -Recurse

$makeappx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "\\x64\\" } | Select-Object -First 1 -ExpandProperty FullName
if (-not $makeappx) {
    $makeappx = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $makeappx) { Write-Error "找不到 makeappx.exe，请安装 Windows SDK。" }

New-Item -ItemType Directory $outDir -Force | Out-Null
$target = Join-Path $outDir "SpellCardHomework.msix"
& $makeappx pack /d $build /p $target /o
Write-Host "MSIX 已生成: $target"
Write-Host ""
Write-Host "上架微软商店：在 Partner Center 提交，微软会重新签名。"
Write-Host "本地侧载测试：需要自签名证书，例如"
Write-Host '  New-SelfSignedCertificate -Type Custom -Subject "CN=Shinichi" -KeyUsage DigitalSignature -FriendlyName "SpellCard" -CertStoreLocation "Cert:\CurrentUser\My" -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")'
Write-Host '  signtool sign /fd SHA256 /a /f cert.pfx /p password "SpellCardHomework.msix"'
