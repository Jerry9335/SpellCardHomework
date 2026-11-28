# 打包说明

## 1. 独立程序（PyInstaller）

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --name "SpellCardHomework" ^
  --icon "assets/icon.ico" --version-file "installer/version_info.txt" ^
  --add-data "assets;assets" ^
  --add-data "tools/ocr_ps.ps1;tools" ^
  --add-data "启动答题浏览器.bat;." ^
  app.pyw
```

产物：`dist\SpellCardHomework\`（内含 `符卡作业簿.exe` 与 `_internal\`）。

## 2. 传统 exe 安装包（Inno Setup 6）

1. 安装 Inno Setup 6（`winget install JRSoftware.InnoSetup`）
2. 编译：

```bat
"D:\Program Files\Inno Setup 7\ISCC.exe" installer\SpellCardHomework.iss
```

产物：`installer\Output\SpellCardHomework-Setup-1.1.7-hotfix.exe`

- 中文语言文件放在 `installer\Languages\ChineseSimplified.isl`
- 用户许可协议在 `installer\EULA.txt`，由 `.iss` 里的 `LicenseFile=EULA.txt` 引用（同样需要 UTF-8 with BOM）
- `.iss` 与 `.ps1` 需要 **UTF-8 with BOM**，否则中文会乱码

## 3. MSIX（微软商店）

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_msix.ps1
```

产物：`installer\Output\SpellCardHomework.msix`

- 需要 Windows SDK（`makeappx.exe`）
- 上架商店时由微软重新签名；本地侧载需自签名证书
- 图标由 `installer\msix\make_logos.py` 从 `assets\icon.ico` 生成

## 版本号

- `SpellCardHomework.iss` 里的 `MyAppVersion`
- `AppxManifest.xml` 里的 `Version="1.1.7.1"`（MSIX 必须是四段）
- 发布前记得同步升级
