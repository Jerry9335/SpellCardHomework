# 符卡作业簿 · 官网（静态页面）

纯 HTML / CSS / JS，无构建步骤、无外部依赖。官网直接放在仓库根目录，和程序源码共用 `assets/`。

## 文件结构

```
/
├── index.html              首页（Hero、三道境界、符卡一览、截图、下载 CTA）
├── features.html           功能介绍 + 东方话术对照表
├── download.html           下载、校验和、安装步骤、授权、常见问题
└── assets/
    ├── css/style.css       全站样式（深色神社 / 红白 / 樱花 / 符卡）
    ├── js/main.js          樱花、导航、入场动画、复制、背景音乐、无刷新换页
    ├── img/                截图、立绘、图标、Hero 背景
    └── audio/
        ├── bgm-1.mp3       背景音乐 1
        └── bgm-2.mp3       背景音乐 2

（`assets/char`、`assets/authors`、`assets/banner.png` 等是程序用的素材，
  官网只引用 `assets/css`、`assets/js`、`assets/img`、`assets/audio`。）
```

## 本地预览

在仓库根目录起一个本地服务器：

```powershell
python -m http.server 8080
# 打开 http://127.0.0.1:8080
```

> 不要直接双击 `index.html`（file://）。背景音乐跨页不断、无刷新换页都依赖 HTTP，
> 用本地服务器或 GitHub Pages 才能看到完整效果。

## 部署到 GitHub Pages

工作流 `.github/workflows/pages.yml` 会从仓库根目录挑出官网文件，
装进 `_site` 再发布，不会把源码 / 安装包 / 文档一起发出去。

1. 把仓库推到 GitHub
2. 仓库 **Settings → Pages → Build and deployment → Source** 选 **GitHub Actions**
3. 推送 `index.html` / `features.html` / `download.html` 或 `assets/css|js|img|audio` 的改动
   （或手动运行 `Deploy site` 工作流）
4. 等 Actions 跑完，访问 `https://jerry9335.github.io/SpellCardHomework/`

## 背景音乐

- 右下角唱片机：点击播放 / 暂停，旁边 ⏭ 切下一首
- 新开标签页随机从两首里选一首，之后 1 → 2 → 1 → 2 循环
- 站内换页采用无刷新切换，音乐不中断
- 浏览器允许自动播放时打开即响；被拦时先静音播放，点**页面任意处**即可开声音
- 刷新页面会从上次进度继续；关闭标签页才停止

## 修改提示

- 版本号写死在 `index.html` 的 kicker、`download.html` 的标题与下载卡片里（搜索 `v1.0.1`）
- 校验和对应 `installer/Output` 里的安装包
- 下载按钮指向 GitHub Releases 的固定版本地址，发版后即可用
- 樱花数量、颜色在 `assets/js/main.js` 的 `COLORS` 与 `count` 里改
- 主色在 `assets/css/style.css` 顶部的 `:root` 变量里改
- 换背景音乐：替换 `assets/audio/bgm-1.mp3` / `bgm-2.mp3`，文件名不变即可
