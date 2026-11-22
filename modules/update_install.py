"""生成并启动更新助手：等待主程序退出、静默安装、提示重启。"""
from __future__ import annotations

import os
import subprocess

_PS = r'''param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [Parameter(Mandatory=$true)][string]$AppDir,
    [Parameter(Mandatory=$true)][string]$AppExe
)
$ErrorActionPreference = 'Stop'
Start-Sleep -Milliseconds 1500
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

function Show-Error($message) {
    [System.Windows.Forms.MessageBox]::Show(
        $message, '博麗神社 · 新号外',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
}

try {
    $dirArg = '/DIR="' + $AppDir + '"'
    $instArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                  '/CLOSEAPPLICATIONS', $dirArg)
    $p = Start-Process -FilePath $Installer -ArgumentList $instArgs `
         -Verb RunAs -Wait -PassThru
    if ($p.ExitCode -ne 0) {
        Show-Error ("紫：结界没有打开，安装没贴成。`n安装包还在取件匣里。`n退出码：" + $p.ExitCode)
        exit 1
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = '博麗神社 · 新号外'
    $form.ClientSize = New-Object System.Drawing.Size(430, 205)
    $form.StartPosition = 'CenterScreen'
    $form.TopMost = $true
    $form.BackColor = [System.Drawing.Color]::FromArgb(12, 9, 18)
    $form.ForeColor = [System.Drawing.Color]::FromArgb(255, 250, 246)
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false

    $title = New-Object System.Windows.Forms.Label
    $title.Text = '文文：新号外已经贴好了。'
    $title.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 13, [System.Drawing.FontStyle]::Bold)
    $title.ForeColor = [System.Drawing.Color]::FromArgb(241, 199, 91)
    $title.SetBounds(26, 24, 380, 30)
    $form.Controls.Add($title)

    $text = New-Object System.Windows.Forms.Label
    $text.Text = '要现在重新开张吗？'
    $text.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 11)
    $text.ForeColor = [System.Drawing.Color]::FromArgb(255, 250, 246)
    $text.SetBounds(26, 66, 380, 26)
    $form.Controls.Add($text)

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = '～ 博麗神社 · 号外张贴完毕 ～'
    $hint.Font = New-Object System.Drawing.Font('Microsoft YaHei UI', 9)
    $hint.ForeColor = [System.Drawing.Color]::FromArgb(214, 200, 223)
    $hint.SetBounds(26, 98, 380, 22)
    $form.Controls.Add($hint)

    $yes = New-Object System.Windows.Forms.Button
    $yes.Text = '现在重开'
    $yes.DialogResult = [System.Windows.Forms.DialogResult]::Yes
    $yes.SetBounds(120, 145, 105, 34)
    $yes.BackColor = [System.Drawing.Color]::FromArgb(179, 56, 68)
    $yes.ForeColor = [System.Drawing.Color]::White
    $yes.FlatStyle = 'Flat'
    $form.Controls.Add($yes)

    $no = New-Object System.Windows.Forms.Button
    $no.Text = '稍后自己开'
    $no.DialogResult = [System.Windows.Forms.DialogResult]::No
    $no.SetBounds(235, 145, 105, 34)
    $no.BackColor = [System.Drawing.Color]::FromArgb(33, 26, 43)
    $no.ForeColor = [System.Drawing.Color]::FromArgb(255, 250, 246)
    $no.FlatStyle = 'Flat'
    $form.Controls.Add($no)

    $form.AcceptButton = $yes
    $form.CancelButton = $no
    $result = $form.ShowDialog()
    if ($result -eq [System.Windows.Forms.DialogResult]::Yes) {
        Start-Process -FilePath $AppExe
    }
} catch {
    Add-Type -AssemblyName System.Windows.Forms
    Show-Error ("紫：结界没有打开，安装没贴成。`n" + $_.Exception.Message)
    exit 1
}
'''


def start_install(installer: str, app_dir: str, app_exe: str) -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "SpellCardHomework", "updates")
    os.makedirs(d, exist_ok=True)
    script = os.path.join(d, "install_update.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(_PS)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", script,
         installer, app_dir, app_exe],
        creationflags=0x08000000,
    )
    return script
