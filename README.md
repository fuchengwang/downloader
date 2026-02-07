# 🚀 高速下载器系统说明文档 (High-Speed Downloader System)

这是一个集成了 Chrome 浏览器插件、Python 下载核心和 macOS 自动化脚本的完整高速下载解决方案。该系统旨在通过 `aria2` 的多线程能力加速文件下载，并主要解决了网盘（如 Quark）下载链接的拦截、Header 捕获和断点续传问题。

## 📂 项目结构

```
downloader/
├── chrome_plugin/          # Chrome 浏览器插件源码
│   └── extension/          # 插件核心文件 (manifest.json, background.js 等)
├── download.py             # Python 下载核心脚本 (基于 aria2c)
└── 下载链接文件.applescript   # macOS 快捷启动脚本
```

## 🛠️ 前置要求 (Prerequisites)

在使用本系统之前，请确保您的 macOS 环境已安装以下软件：

1.  **Python 3**: macOS 通常自带，可通过 `python3 --version` 检查。
2.  **aria2**: 核心下载引擎。
    *   安装命令: `brew install aria2` (需要 Homebrew)
    *   或者通过其他方式安装，确保 `aria2c` 命令在终端可用。

## 📦 安装与配置

### 1. 安装 Chrome 插件
1.  打开 Chrome 浏览器，进入扩展程序管理页面 (`chrome://extensions/`)。
2.  开启右上角的 **"开发者模式"**。
3.  点击 **"加载已解压的扩展程序"**。
4.  选择本项目中的 `downloader/chrome_plugin/extension` 目录。
5.  插件加载成功后，您应该能看到 "下载链接捕捉器" 图标。

### 2. 配置启动脚本 (可选)
`下载链接文件.applescript` 提供了一个快捷方式来启动下载终端。
*   **使用方法**: 您可以直接在 Script Editor 中运行，或者将其导出为 macOS 应用程序 (`.app`) 放置在 Dock 栏。
*   **注意**: 脚本中默认使用 `./download.py` 相对路径。如果您将其导出为 App 运行，建议将脚本中的路径修改为绝对路径 (例如: `do script "python3 /Users/yourname/path/to/downloader/download.py"`), 以免出现 "找不到文件" 的错误。

---

## 💻 使用指南 (User Guide)

### 第一步：触发下载
在 Chrome 浏览器中点击任意文件的下载链接（例如 Quark 网盘的下载按钮）。

### 第二步：插件拦截
插件会自动拦截浏览器的默认下载请求，并弹出一个对话框。
*   **对话框显示内容**: 被拦截的 URL 和自动生成的下载命令。
*   **操作**: 点击 **"复制命令" (Copy Command)** 按钮。
    *   *此时，包含 URL、Cookie、User-Agent 等完整信息的下载命令已复制到您的剪贴板。*

### 第三步：启动下载器
运行 `下载链接文件.applescript` (或直接在终端运行 `python3 download.py`)。终端窗口将启动并显示提示：
> `请输入下载链接 (或输入 'v' 从剪贴板读取):`

### 第四步：开始下载
在终端中输入 **`v`** 并按回车。
*   脚本会自动读取剪贴板中的命令。
*   智能解析出 URL 和必要的 Headers (如 Cookie)。
*   调用 `aria2c` 开启多线程高速下载。


---

## 🔧 高级功能与故障排除

### 1. 为什么需要拦截?
很多网盘（如 Quark）的下载链接具有时效性，且绑定了特定的 `Cookie` 和 `Referer`。直接复制链接到迅雷或其他工具往往会因为鉴权失败而导致下载速度为 0 或 403 Forbidden。
本系统的插件会精确捕获发起请求时的所有 Headers，并将其传递给 `aria2`，完美模拟浏览器行为，确保全速下载。

### 2. 手动模式
如果您不想使用插件，也可以手动运行脚本下载普通链接：
```bash
python3 download.py "https://example.com/file.zip"
```

### 3. 使用 Curl 下载
如果 `aria2` 遇到问题，脚本支持回退到 `curl` 单线程下载模式：
```bash
python3 download.py --curl "URL..."
```
或者在交互模式中，脚本逻辑目前默认优先使用 `aria2`，如需强制 `curl` 可通过命令行参数指定。

### 4. 常见问题
*   **报错 "未找到 aria2c"**: 请确保即使在终端能运行，脚本也能找到它。通常 `brew install` 的路径 `/opt/homebrew/bin/aria2c` 是自动识别的。
*   **下载速度为 0**: 可能是 Cookie 过期。请关闭终端，并在浏览器中重新刷新页面点击下载，获取最新的拦截命令。
