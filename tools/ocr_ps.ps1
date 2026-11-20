param(
  [Parameter(Mandatory = $false)][string]$ImagePath,
  [string]$Languages = "zh-Hans-CN,en-US",
  [switch]$ListLanguages
)
$ErrorActionPreference = "Stop"
$OutputEncoding = [System.Text.Encoding]::UTF8
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

function Emit($obj) {
  [Console]::Out.WriteLine(($obj | ConvertTo-Json -Depth 8 -Compress))
}

try { Add-Type -AssemblyName System.Runtime.WindowsRuntime | Out-Null } catch {}

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
  })[0]

function Await($op, $resultType) {
  $t = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
  $t.Wait(-1) | Out-Null
  if ($t.IsFaulted) { throw ($t.Exception.Flatten().InnerException.Message) }
  $t.Result
}

[Windows.Storage.Streams.InMemoryRandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Storage.Streams.DataWriter, Windows.Storage.Streams, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null

if ($ListLanguages) {
  $langs = @()
  foreach ($l in [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages) {
    $langs += [pscustomobject]@{ tag = $l.LanguageTag; name = $l.DisplayName }
  }
  Emit ([pscustomobject]@{ ok = $true; languages = $langs })
  exit 0
}

if ([string]::IsNullOrWhiteSpace($ImagePath) -or -not (Test-Path -LiteralPath $ImagePath)) {
  Emit ([pscustomobject]@{ ok = $false; error = "image_not_found"; path = $ImagePath })
  exit 0
}

# 用 .NET 读文件 + 内存流解码，绕开 Windows.Storage 对桌面进程的路径限制
$fullPath = (Resolve-Path -LiteralPath $ImagePath).Path
$bytes = [System.IO.File]::ReadAllBytes($fullPath)

$ras = New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
$writer = New-Object Windows.Storage.Streams.DataWriter($ras)
$writer.WriteBytes($bytes)
$null = Await ($writer.StoreAsync()) ([uint32])
$writer.DetachStream() | Out-Null
$null = $ras.Seek(0)

$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($ras)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync(
    [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8,
    [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied)) ([Windows.Graphics.Imaging.SoftwareBitmap])

$results = @()
$requested = @($Languages -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($requested.Count -eq 0) { $requested = @("") }

foreach ($langTag in $requested) {
  $engine = $null
  if ($langTag) {
    try {
      $lang = New-Object Windows.Globalization.Language $langTag
      $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
    } catch { $engine = $null }
  }
  if ($null -eq $engine) {
    $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
  }
  if ($null -eq $engine) { continue }

  $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  $lines = New-Object System.Collections.ArrayList
  foreach ($line in $res.Lines) {
    if ($line.Words.Count -eq 0) { continue }
    $minX = [double]::MaxValue; $minY = [double]::MaxValue; $maxX = 0.0; $maxY = 0.0
    foreach ($w in $line.Words) {
      $r = $w.BoundingRect
      if ($r.X -lt $minX) { $minX = $r.X }
      if ($r.Y -lt $minY) { $minY = $r.Y }
      if (($r.X + $r.Width) -gt $maxX) { $maxX = $r.X + $r.Width }
      if (($r.Y + $r.Height) -gt $maxY) { $maxY = $r.Y + $r.Height }
    }
    [void]$lines.Add([pscustomobject]@{
        t = $line.Text
        x = [math]::Round($minX, 1)
        y = [math]::Round($minY, 1)
        w = [math]::Round($maxX - $minX, 1)
        h = [math]::Round($maxY - $minY, 1)
      })
  }
  $text = (($res.Lines | ForEach-Object { $_.Text }) -join "`n")
  $results += [pscustomobject]@{
    lang  = $engine.RecognizerLanguage.LanguageTag
    text  = $text
    lines = $lines
    count = $res.Lines.Count
  }
}

Emit ([pscustomobject]@{
    ok     = $true
    width  = $decoder.PixelWidth
    height = $decoder.PixelHeight
    results = $results
  })
