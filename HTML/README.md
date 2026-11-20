# 符卡作业簿 · 官网（静态页面）

纯 HTML / CSS / JS，无构建步骤、无外部依赖，双击 `index.html` 就能看。

## 文件结构

```
HTML/
├── index.html            首页（Hero、三道境界、符卡一览、截图、下载 CTA）
├── features.html         功能介绍 + 东方话术对照表
├── download.html         下载、校验和、安装步骤、授权、常见问题
└── assets/
    ├── css/style.css     全站样式（深色神社 / 红白 / 樱花 / 符卡）
    ├── js/main.js        樱花飘落、导航、入场动画、复制校验和
    └── img/              截图、立绘、图标、Hero 背景
```

## 本地预览

直接双击 `HTML/index.html`，或起一个本地服务器：

```powershell
cd HTML
python -m http.server 8080
# 打开 http://127.0.0.1:8080
```

## 部署到 GitHub Pages

仓库里已经放了工作流 `.github/workflows/pages.yml`，它会把 `HTML/` 发布为 Pages。

1. 把整个仓库推到 GitHub
2. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
3. 推送 `HTML/` 的改动（或手动运行 `Deploy site` 工作流）
4. 等 Actions 跑完，访问 `https://jerry9335.github.io/SpellCardHomework/`

> 如果不想用 Actions，也可以把 `HTML/` 的内容推到 `gh-pages` 分支，
> 然后在 Pages 里选择「Deploy from a branch → gh-pages」。

## 修改提示

- 版本号写死在 `index.html` 的 kicker、`download.html` 的标题与下载卡片里（搜索 `v1.0.1`）
- 校验和对应 `installer/Output` 里的两个安装包
- 下载按钮指向 GitHub Releases 的固定版本地址，发版后即可用
- 樱花数量、颜色在 `assets/js/main.js` 的 `COLORS` 与 `count` 里改
- 主色在 `assets/css/style.css` 顶部的 `:root` 变量里改
