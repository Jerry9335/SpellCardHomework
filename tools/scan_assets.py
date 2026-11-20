"""用 Windows Defender 扫描 assets 目录（下载素材后的安全检查）。"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TARGET = os.path.join(ROOT, "assets")


def main() -> int:
    mp = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                      "Windows Defender", "MpCmdRun.exe")
    if not os.path.exists(mp):
        print("找不到 MpCmdRun.exe，改用手动方式：用 Windows 安全中心扫一扫 assets 目录。")
        return 2
    print(f"扫描：{TARGET}")
    proc = subprocess.run([mp, "-Scan", "-ScanType", "3", "-File", TARGET, "-DisableRemediation"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.strip()[-800:])
    return 0 if proc.returncode == 0 and "no threats" in out.lower() else 1


if __name__ == "__main__":
    sys.exit(main())
