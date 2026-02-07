/**
 * 下载链接捕捉器 - 后台脚本
 * 截获下载链接和请求头，提供复制或继续下载选项
 */

// 存储最近的请求头信息 (URL -> headers)
const recentRequestHeaders = new Map();

// 存储被拦截的下载信息（用于重新下载）
const interceptedDownloads = new Map();

// 等待中的合法下载计数（用于跳过我们自己创建的下载）
let pendingDownloadCount = 0;

// 清理过期数据
setInterval(() => {
    const now = Date.now();
    for (const [url, data] of recentRequestHeaders) {
        if (now - data.timestamp > 30000) {
            recentRequestHeaders.delete(url);
        }
    }
    for (const [id, data] of interceptedDownloads) {
        if (now - data.timestamp > 300000) {
            interceptedDownloads.delete(id);
        }
    }
}, 10000);

// 监听所有请求，捕获 headers
chrome.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
        if (details.type === 'main_frame' || details.type === 'sub_frame' ||
            details.type === 'xmlhttprequest' || details.type === 'other') {

            const headers = {};
            if (details.requestHeaders) {
                for (const header of details.requestHeaders) {
                    const name = header.name.toLowerCase();
                    // 在有 extraHeaders 的情况下，我们可以捕获 Cookie 和 Authorization
                    if (['cookie', 'referer', 'user-agent', 'authorization', 'origin'].includes(name)) {
                        headers[header.name] = header.value;
                    }
                }
            }

            recentRequestHeaders.set(details.url, {
                headers: headers,
                timestamp: Date.now()
            });
        }
    },
    { urls: ["<all_urls>"] },
    ["requestHeaders", "extraHeaders"] // 关键：添加 extraHeaders 以获取 Cookie 等敏感头
);

// 监听下载创建事件
chrome.downloads.onCreated.addListener(async (downloadItem) => {
    const finalUrl = downloadItem.finalUrl || downloadItem.url;

    console.log('[下载捕捉] 检测到新下载, ID:', downloadItem.id);

    // 检查是否是我们自己创建的下载（通过计数器）
    if (pendingDownloadCount > 0) {
        pendingDownloadCount--;
        console.log('[下载捕捉] 这是用户确认的下载，跳过拦截');
        return; // 不拦截
    }

    // 立即取消下载
    try {
        await chrome.downloads.cancel(downloadItem.id);
        console.log('[下载捕捉] 已取消下载');
    } catch (err) {
        console.log('[下载捕捉] 取消失败:', err);
    }

    // 1. 尝试从 webRequest 缓存查找 headers
    let headers = {};
    if (recentRequestHeaders.has(finalUrl)) {
        headers = { ...recentRequestHeaders.get(finalUrl).headers };
    } else if (recentRequestHeaders.has(downloadItem.url)) {
        headers = { ...recentRequestHeaders.get(downloadItem.url).headers };
    } else {
        // 模糊匹配
        const baseUrl = finalUrl.split('?')[0];
        for (const [url, data] of recentRequestHeaders) {
            if (url.startsWith(baseUrl)) {
                headers = { ...data.headers };
                break;
            }
        }
    }

    // 2. 检查并补全 Cookie (最关键的修正)
    // 如果 headers 里没有 Cookie，或者我们想确保拿到最新的 Cookie
    // 直接查询浏览器 cookie store 是最稳健的方法
    try {
        // 先获取当前下载链接对应的 cookie
        let cookieList = await chrome.cookies.getAll({ url: finalUrl });

        // 针对夸克网盘的特殊处理：确保拿到 pan.quark.cn 的鉴权 Cookie
        // 因为 CDN 域名 (dl-*.quark.cn) 可能无法正确获取到种在 pan.quark.cn 下的所有 Cookie
        if (finalUrl.includes('quark.cn')) {
            try {
                const mainDomainCookies = await chrome.cookies.getAll({ url: 'https://pan.quark.cn' });
                if (mainDomainCookies) {
                    // 使用 Map 进行去重和合并
                    // 默认保留 cookieList 中已有的 (认为它们更具体匹配当前 URL)
                    // 补充 mainDomainCookies 中有的但 cookieList 中没有的
                    const existingNames = new Set(cookieList.map(c => c.name));

                    for (const c of mainDomainCookies) {
                        if (!existingNames.has(c.name)) {
                            cookieList.push(c);
                            existingNames.add(c.name);
                        }
                    }
                    console.log(`[下载捕捉] 合并了 pan.quark.cn 的 Cookie，当前总数: ${cookieList.length}`);
                }
            } catch (err) {
                console.warn('[下载捕捉] 获取主域 Cookie 失败:', err);
            }
        }

        if (cookieList && cookieList.length > 0) {
            // 将 cookie 对象数组转换为 "name=value; name2=value2" 字符串
            const cookieString = cookieList.map(c => `${c.name}=${c.value}`).join('; ');

            // 如果 headers 里已经有 cookie，我们可以选择覆盖或者合并
            // 这里选择优先使用 active query 得到的 cookie，因为它是最准确的当前状态
            headers['Cookie'] = cookieString;
            console.log(`[下载捕捉] 主动获取并生成了 Cookie 字符串`);
        }
    } catch (e) {
        console.warn('[下载捕捉] 获取 Cookie 失败 (可能缺少权限):', e);
    }

    // 3. 补全 User-Agent (如果你没有 webRequest 捕获到，就用当前浏览器的)
    if (!headers['User-Agent'] && !headers['user-agent']) {
        headers['User-Agent'] = navigator.userAgent;
    }

    // 4. 补全 Referer (优先用 downloadItem 自带的，它比 webRequest 更能反映下载来源)
    if (downloadItem.referrer && !headers['Referer'] && !headers['referer']) {
        headers['Referer'] = downloadItem.referrer;
    }

    console.log('[下载捕捉] 最终捕获到的 Headers:', Object.keys(headers));

    // 构建完整的下载命令字符串
    const downloadCommand = buildDownloadCommand(finalUrl, headers);

    // 生成唯一的拦截 ID
    const interceptId = Date.now().toString();

    // 保存拦截信息
    interceptedDownloads.set(interceptId, {
        url: finalUrl,
        filename: downloadItem.filename || '',
        headers: headers,
        timestamp: Date.now()
    });

    // 获取当前窗口以计算中心位置
    try {
        // 使用 promise 包装 chrome.windows.getLastFocused 以便使用 await (如果支持) 
        // 或者保留回调风格，这里保持逻辑不变只是修正 headers
        chrome.windows.getLastFocused((lastFocusedWindow) => {
            const width = 450;
            const height = 280;

            let left = 0;
            let top = 0;

            if (lastFocusedWindow) {
                left = Math.round(lastFocusedWindow.left + (lastFocusedWindow.width - width) / 2);
                top = Math.round(lastFocusedWindow.top + (lastFocusedWindow.height - height) / 2);
            }

            chrome.windows.create({
                url: `dialog.html?interceptId=${interceptId}&url=${encodeURIComponent(finalUrl)}&command=${encodeURIComponent(downloadCommand)}`,
                type: 'popup',
                width: width,
                height: height,
                left: left,
                top: top,
                focused: true
            });
        });
    } catch (e) {
        console.error("创建窗口失败", e);
    }
});

/**
 * 规范化 URL，对查询参数中的特殊字符进行编码
 * 主要处理 response-content-disposition 等参数中未编码的 ; 和空格
 * 强制匹配 Quark 服务器要求的严格编码格式 (如 %3B 代替 ;)
 */
function normalizeUrl(originalUrl) {
    try {
        const urlObj = new URL(originalUrl);
        const searchParams = urlObj.searchParams;
        const newParams = new URLSearchParams();

        // 遍历每个参数，重新编码
        for (const [key, value] of searchParams) {
            newParams.append(key, value);
        }

        let searchString = newParams.toString();

        // 关键修复：手动替换特殊字符以匹配服务器要求
        // 1. 将 ; 替换为 %3B (修复403的关键)
        searchString = searchString.replace(/;/g, '%3B');
        // 2. 将 + (可能代表空格) 替换为标准的 %20
        searchString = searchString.replace(/\+/g, '%20');

        urlObj.search = searchString;
        return urlObj.toString();
    } catch (e) {
        console.warn('[下载捕捉] URL 规范化失败，使用原始 URL:', e);
        return originalUrl;
    }
}

/**
 * 构建下载命令字符串（URL + Headers）
 */
function buildDownloadCommand(url, headers) {
    // 先对 URL 进行规范化编码，避免 shell 截断问题
    const normalizedUrl = normalizeUrl(url);
    let command = `"${normalizedUrl}"`;

    for (const [name, value] of Object.entries(headers)) {
        // 忽略空的 header
        if (!value) continue;

        // 处理 value 中的双引号
        const escapedValue = String(value).replace(/"/g, '\\"');
        command += ` --header "${name}: ${escapedValue}"`;
    }

    return command;
}

// 监听来自弹窗的消息
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'start-download') {
        const interceptData = interceptedDownloads.get(message.interceptId);
        if (interceptData) {
            startDownload(interceptData);
            interceptedDownloads.delete(message.interceptId);
        }
        sendResponse({ success: true });
    } else if (message.type === 'copy-to-clipboard') {
        copyToClipboard(message.text).then(() => {
            sendResponse({ success: true });
        });
        return true;
    } else if (message.type === 'cancel-intercept') {
        interceptedDownloads.delete(message.interceptId);
        sendResponse({ success: true });
    } else if (message.type === 'get-download-data') {
        // 新增：允许前端主动拉取数据，避免 URL 参数截断问题
        const interceptData = interceptedDownloads.get(message.interceptId);
        if (interceptData) {
            const downloadCommand = buildDownloadCommand(interceptData.url, interceptData.headers);
            sendResponse({
                success: true,
                url: interceptData.url,
                command: downloadCommand
            });
        } else {
            sendResponse({ success: false });
        }
        return true;
    }
    return true;
});

/**
 * 重新开始下载
 */
async function startDownload(interceptData) {
    console.log('[下载捕捉] 重新开始下载:', interceptData.url.substring(0, 80));

    // 增加计数器，让下一个 onCreated 事件跳过拦截
    pendingDownloadCount++;

    try {
        await chrome.downloads.download({
            url: interceptData.url,
            saveAs: false
        });
        console.log('[下载捕捉] 下载已重新开始');
    } catch (err) {
        console.error('[下载捕捉] 重新下载失败:', err);
        // 失败时回滚计数器
        pendingDownloadCount = Math.max(0, pendingDownloadCount - 1);
    }
}

/**
 * 复制文本到剪贴板
 */
async function copyToClipboard(text) {
    const existingContexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT']
    });

    if (existingContexts.length === 0) {
        await chrome.offscreen.createDocument({
            url: 'offscreen.html',
            reasons: ['CLIPBOARD'],
            justification: '复制下载链接到剪贴板'
        });
    }

    await chrome.runtime.sendMessage({
        target: 'offscreen',
        type: 'copy',
        text: text
    });

    console.log('[下载捕捉] 已复制到剪贴板');
}
