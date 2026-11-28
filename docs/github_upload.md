# GitHub 上传清单（v1.0.1）

## 一、仓库名建议

| 仓库名 | 说明 |
| --- | --- |
| **`SpellCardHomework`**（推荐） | 和 exe 同名，最好记，搜索友好 |
| `spellcard-homework` | 短横线风格 |
| `GensokyoHomework` | 东方味更浓 |
| `SpellCardWorksheet` | 作业簿直译 |

推荐：

- 仓库名：`SpellCardHomework`
- 描述：`东方 Project 风格的 Windows 截屏识题 + AI 作答 + 全自动网页答题工具`
- Topics：`touhou` `windows` `tkinter` `ocr` `ai` `homework` `automation` `python`

## 二、上传前必做

- [ ] **备份私钥**：`license_private.key` 拷到 U 盘 / 密码管理器 / 另一台电脑（丢了就签不出新激活码）
- [ ] **备份发码工具**：`发码工具.pyw`（不进仓库，但本地要留）
- [ ] 确认 `.gitignore` 已包含：
  `license_private.key`、`license.json`、`config.json`、`发码工具.pyw`、`assets_candidates/`、`Pictures/`、`backup_license_*/`、`backup_appdata_*/`、`dist/`、`build/`、`installer/Output/`
- [ ] 检查没有 API Key 泄漏：
  ```powershell
  git grep -n "sk-" ; git grep -n "license_private"
  ```
- [ ] 版本号一致（都应显示 1.0.1）：
  - `modules/settings.py` → `APP_VERSION`
  - `installer/version_info.txt`
  - `installer/SpellCardHomework.iss` → `MyAppVersion`
  - `installer/msix/AppxManifest.xml` → `Version`
- [ ] `docs/` 里没有临时截图（`_*.png`、`main_new.png` 之类）

## 三、上传文件清单

### 根目录

| 文件 | 说明 | 上传 |
| --- | --- | --- |
| `app.pyw` | 主程序 | ✅ |
| `README.md` / `README.en.md` | 中文 / 英文说明（含 v1.0.1 更新日志） | ✅ |
| `LICENSE` | MIT | ✅ |
| `.gitignore` | 忽略私钥与构建产物 | ✅ |
| `启动答题浏览器.bat` | 启动带调试端口的 Edge | ✅ |
| `启动（调试）.bat` | 源码调试启动 | ✅ |
| `符卡作业簿.exe` | 旧启动器 | ❌（已在 .gitignore） |
| `发码工具.pyw` | 作者发码器 | ❌（已在 .gitignore） |

### `modules/`

`capture.py`、`clipboard.py`、`web.py`、`llm.py`、`latex.py`、`prompts.py`、`settings.py`、`usage.py`、`license.py`、`license_sign.py`、`ed25519.py`、`__init__.py`

> `license_sign.py` 只是签名代码，不含私钥；私钥在 `license_private.key`，不会上传。

### `assets/`

`banner.png`、`splash.png`、`icon.png`、`icon.ico`、`char/`（AI 立绘）、`authors/`

### `tools/`

测试与开发脚本：`make_assets.py`、`apply_pictures.py`、`splash_text.py`、`license_keygen.py`、`launcher.cs`、`ocr_ps.ps1`、`test_*.py`、`shot_*.py`、`mock_server.py` 等

### `installer/`

| 文件 | 说明 |
| --- | --- |
| `SpellCardHomework.iss` | Inno Setup 7 安装脚本（含 EULA、卸载清理、重置授权任务） |
| `EULA.txt` | 最终用户许可协议（UTF-8 BOM） |
| `version_info.txt` | exe 版本信息 |
| `Languages/ChineseSimplified.isl` | 中文安装界面 |
| `msix/AppxManifest.xml`、`msix/make_logos.py`、`msix/Assets/*` | MSIX 清单与图标 |
| `build_msix.ps1` | MSIX 打包脚本 |
| `README.md` | 打包说明 |
| `Output/` | 构建产物 | ❌ 不上传 |

### `docs/`

| 文件 | 用途 |
| --- | --- |
| `main.png`、`splash.png`、`settings.png`、`usage.png`、`about_app.png`、`about_authors.png` | README 截图 |
| `activation_firstrun.png`、`activation_expired.png` | 首次启动 / 到期截图 |
| `installer_eula.png` | 安装许可页截图 |
| `keygen.png` | 发码工具截图 |
| `author_licensing.md` | 发码流程（不含私钥） |
| `github_upload.md` | 本清单 |
| `banner.png` | 横幅素材 |

## 四、绝对不要上传

| 路径 | 原因 |
| --- | --- |
| `license_private.key` | **签名私钥**，泄露 = 别人能自己发码 |
| `发码工具.pyw` | 作者专用发码器 |
| `assets_candidates/` | 网络下载的候选图，授权不明 |
| `Pictures/` | AI 原图（约 55 MB），仓库不需要 |
| `backup_license_*/`、`backup_appdata_*/` | 旧授权模块/数据备份（含旧密钥） |
| `dist/`、`build/`、`installer/Output/`、`*.spec` | 构建产物 |
| `%APPDATA%` 下的 `license.json`、`config.json`、`usage.jsonl`、`boot.log` | 本机配置与记录 |

## 五、上传命令

```powershell
cd D:\zack\Desktop\Develop\Shinichi-Exercise-Tools

git init
git add .
git status
```

**逐项检查 `git status` 列表**，确认没有私钥、发码工具、候选图、构建产物。再执行：

```powershell
git ls-files | Select-String "license_private|发码工具|assets_candidates|Pictures|^dist/|^build/|^installer/Output/"
```

**没有任何输出**才继续：

```powershell
git commit -m "Initial commit: SpellCardHomework 1.0.1"
git branch -M main
git remote add origin https://github.com/Jerry9335/SpellCardHomework.git
git push -u origin main
```

## 六、GitHub 仓库设置

- Description：`东方 Project 风格的 Windows 截屏识题 + AI 作答 + 全自动网页答题工具`
- Topics：`touhou` `windows` `tkinter` `ocr` `ai` `homework` `automation` `python`
- License：MIT（自动识别 `LICENSE`）
- 关闭 Wiki / Projects

## 七、Release（安装包不进仓库）

1. Releases → Create a new release
2. Tag：`v1.0.1`，标题：`SpellCardHomework 1.0.1`
3. 上传：
   - `installer/Output/SpellCardHomework-Setup-1.0.1.exe`
4. 发布说明可以写：

```
v1.0.1
- 授权升级为 Ed25519 非对称签名
- 首次启动先弹授权窗口，可试用 3 天
- 新增启动日志 boot.log
- 卸载清除授权记录
- 安装包加入用户许可协议 + 可选「清除本机授权」
- 设置窗口可滚动，关于/作者窗口自适应
- 启动图/版本号统一 1.0.1
```

## 八、上传后自查

- [ ] GitHub 搜索 `license_private`、`PRIVATE KEY`、`sk-`，无结果
- [ ] `发码工具.pyw`、`Pictures/`、`assets_candidates/` 不在仓库里
- [ ] README 截图显示正常
- [ ] Releases 安装包可下载、可安装
- [ ] 首次安装弹出「博麗神社 · 结界许可」

## 九、私钥与发码工具保管

- 放在**单独的加密文件夹 / U 盘**，不要放仓库目录以外的公开网盘
- 换电脑、重装系统前先备份
- 私钥丢失 = 无法再发新码，只能换密钥并发布新版本
