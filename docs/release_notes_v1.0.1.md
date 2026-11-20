# SpellCardHomework 1.0.1

> 东方 Project 风格的 Windows 截屏识题 + AI 作答 + 全自动网页答题工具
> Touhou-style screenshot OCR + AI answering + auto web answering for Windows

---

## 中文

### 概要

`SpellCardHomework 1.0.1` 是首个公开版本：截屏识题 → 英文翻译 → AI 作答 → 全自动网页答题，附带用量账本、余额查询与一机一码授权。

### 主要功能

- **截屏识别（F8）**：全屏 / 窗口 / 框选，Windows OCR 或视觉模型
- **公式渲染**：LaTeX → √、x²、≤、∑、矩阵
- **英文题自动翻译**
- **AI 作答**：DeepSeek / OpenAI / 智谱 / 通义 / OpenRouter / 本地 Ollama
- **全自动网页答题**：CDP 接管 Edge / Chrome，单选、多选、填空、下拉、多小问、答错重试
- **香火钱账本**：每次调用的 tokens、耗时、费用估算，30 天柱状图，CSV 导出
- **查余额**：DeepSeek 账户余额
- **一机一码**：Ed25519 签名，首次启动可选 5 天试用

### 本次更新（相对内部 1.0.0）

- 授权升级为 **Ed25519 非对称签名**：程序里只放公钥，源码公开也无法伪造激活码
- **首次启动先弹授权窗口**：可选「先试用 5 天」或粘贴激活码，不再直接进主界面
- 新增 **启动日志** `%APPDATA%\SpellCardHomework\boot.log`，记录 `access=licensed/trial/fresh/expired`
- 显示主界面前**二次校验授权**，没有许可/试用直接退出
- **卸载自动清除授权与试用记录**（保留设置与 API Key）
- 安装包新增 **《最终用户许可协议》** 页面，需同意才能继续
- 安装包新增可选任务 **「清除本机授权与试用记录（重新激活）」**
- 设置窗口支持**滚动**，底部按钮固定；关于程序 / 关于作者窗口**自适应大小**
- 安装版 exe 带「符卡作业簿」文件描述和灵梦图标；启动图版本号同步为 v1.0.1

### 安装

1. 下载 `SpellCardHomework-Setup-1.0.1.exe` 双击安装
2. 阅读并同意用户许可协议
3. 首次启动会弹出「博麗神社 · 结界许可」：
   - 点「先试用 5 天」直接试用
   - 或复制「本机灵符」发邮件申请激活码

> MSIX 包 `SpellCardHomework.msix` 供侧载/商店使用，本地侧载需要签名。

### 系统要求

- Windows 10 / 11（x64）
- 安装包无需 Python；源码运行需要 Python 3.10+ 与 Pillow
- 全自动答题需要 Edge 或 Chrome

### 已知限制

- 单机离线授权只能防住"删文件/改时间"级别的绕过，防不住逆向修改
- 卸载会清除授权，重装后需要重新试用或激活
- 1.0.1 之前的旧激活码（短码）已作废
- 自动答题涉及第三方平台条款，请自行确认使用场景

### 校验和（SHA256）

```
SpellCardHomework-Setup-1.0.1.exe
414C4A020436BFC43C11B37FAFA1D7C69CBBBB322BA199C9AF11D0D8783DA434

SpellCardHomework.msix
F5C690DC05EB5538234DEF2E236961AE5D649FBFEBDB10CE0C160A8C1818D70C
```

---

## English

### Overview

`SpellCardHomework 1.0.1` is the first public release: screenshot OCR → translation → AI answering → fully automatic web answering, with a usage ledger, balance check and one-machine-one-code licensing.

### Highlights

- Screenshot OCR (F8): full screen / window / region, Windows OCR or vision model
- Formula rendering (LaTeX → √, x², ≤, ∑, matrices)
- Automatic English-to-Chinese translation
- AI answering via DeepSeek / OpenAI / Zhipu / Qwen / OpenRouter / local Ollama
- Fully automatic web answering through CDP (Edge/Chrome): radios, checkboxes, fill-ins, dropdowns, multi-part questions, retries
- Usage ledger: tokens, duration and estimated cost per call, 30-day chart, CSV export
- Balance check (DeepSeek)
- Ed25519 licensing with a 5-day trial on first launch

### Changes in 1.0.1

- Licensing moved to **Ed25519 asymmetric signatures** (public key only in the app)
- First launch **always shows the activation window** (5-day trial or activation code)
- Boot log at `%APPDATA%\SpellCardHomework\boot.log`
- Access is re-verified right before the main window appears
- **Uninstall now clears license and trial records** (settings and API key are kept)
- Installer adds the **End User License Agreement** page
- Installer adds an optional **"clear local license"** task
- Settings window is **scrollable** with a fixed footer; About / Authors dialogs auto-size
- Installed exe has the proper file description and Reimu icon; splash shows v1.0.1

### Install

1. Run `SpellCardHomework-Setup-1.0.1.exe`
2. Accept the license agreement
3. On first launch choose **"start 5-day trial"** or send the machine code to the authors for an activation code

### Requirements

- Windows 10 / 11 (x64)
- No Python needed with the installer; source runs need Python 3.10+ and Pillow
- Edge or Chrome for web automation

### Known limitations

- Offline licensing stops casual tampering, not reverse engineering
- Uninstalling clears the license; reinstallation requires a new trial/activation
- Codes issued before 1.0.1 are invalid
- Web automation is subject to third-party platform terms

### Checksums (SHA256)

```
SpellCardHomework-Setup-1.0.1.exe
414C4A020436BFC43C11B37FAFA1D7C69CBBBB322BA199C9AF11D0D8783DA434

SpellCardHomework.msix
F5C690DC05EB5538234DEF2E236961AE5D649FBFEBDB10CE0C160A8C1818D70C
```
