# 符卡作业簿 · 官网（docs 目录）

官网全部放在 **`docs/`**，GitHub Pages 直接从 `main` 的 `/docs` 发布。
纯 HTML / CSS / JS，无构建步骤、无外部依赖。

## 文件结构

```
docs/
├── index.html              首页（Hero、三道境界、符卡一览、截图、下载 CTA）
├── features.html           功能介绍 + 东方话术对照表
├── download.html           下载、校验和、安装步骤、授权、常见问题
├── website.md              本说明
└── assets/
    ├── css/style.css       全站样式（深色神社 / 红白 / 樱花 / 符卡）
    ├── js/main.js          樱花、导航、入场动画、复制、背景音乐、无刷新换页
    ├── img/                截图、立绘、图标、Hero 背景
    └── audio/
        ├── bgm-1.mp3       背景音乐 1
        └── bgm-2.mp3       背景音乐 2
```

> 仓库根目录的 `assets/` 只放程序素材（`char/`、`authors/`、`banner.png`、`icon.*`、
> `splash.png`、`toast_icon.png`），官网只引用 `docs/assets/` 下的文件。

## 本地预览

在仓库根目录起一个本地服务器，把 `docs` 作为站点目录：

```powershell
python -m http.server 8080 --directory docs
# 打开 http://127.0.0.1:8080
```

> 不要直接双击 `docs/index.html`（file://）。背景音乐跨页不断、无刷新换页都依赖 HTTP，
> 用本地服务器或 GitHub Pages 才能看到完整效果。

## 部署到 GitHub Pages

当前 Pages 源是 **`main` 分支的 `/docs` 目录**：

1. 改完 `docs/` 里的文件，直接提交并推送到 `main`
2. GitHub Pages 会自动构建 `/docs`
3. 等 Actions 里的 `pages build and deployment` 跑完，访问
   `https://jerry9335.github.io/SpellCardHomework/`

不需要额外的工作流；仓库里只保留 Pages 自带的部署流程。

## 背景音乐

- 右下角唱片机：点击播放 / 暂停，旁边 ⏭ 切下一首
- 新开标签页随机从两首里选一首，之后 1 → 2 → 1 → 2 循环
- 站内换页采用无刷新切换，音乐不中断
- 打开即自动播放；若浏览器拦截带声音的自动播放，会先静音起播，首次点击/按键后自动开声（不再显示「点击任意处」提示）
- 刷新页面会从上次进度继续；关闭标签页才停止

## 修改提示

- 版本号写死在 `docs/index.html` 的 kicker、`docs/download.html` 的标题与下载卡片里（搜索 `v1.0.1`）
- 校验和对应 `installer/Output` 里的安装包
- 下载按钮指向 GitHub Releases 的固定版本地址，发版后即可用
- 樱花数量、颜色在 `docs/assets/js/main.js` 的 `COLORS` 与 `count` 里改
- 主色在 `docs/assets/css/style.css` 顶部的 `:root` 变量里改
- 换背景音乐：替换 `docs/assets/audio/bgm-1.mp3` / `bgm-2.mp3`，文件名不变即可
