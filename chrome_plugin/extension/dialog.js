/**
 * 对话框脚本
 */

// 解析 URL 参数
const params = new URLSearchParams(window.location.search);
const interceptId = params.get('interceptId');
// 保留 URL 参数作为备用显示，但主要依赖消息拉取
let currentUrl = decodeURIComponent(params.get('url') || '');
let currentCommand = decodeURIComponent(params.get('command') || '');

// 初始化显示
document.getElementById('url').textContent = currentUrl || '加载中...';
document.getElementById('command').textContent = currentCommand || '正在获取完整命令...';

// 主动拉取完整数据（解决 URL 长度限制导致的截断问题）
chrome.runtime.sendMessage({
    type: 'get-download-data',
    interceptId: interceptId
}, (response) => {
    if (response && response.success) {
        console.log('成功拉取完整下载数据');
        currentUrl = response.url;
        currentCommand = response.command;

        document.getElementById('url').textContent = currentUrl;
        document.getElementById('command').textContent = currentCommand;
    } else {
        console.warn('拉取数据失败，使用 URL 参数作为降级方案');
    }
});

// 复制到剪贴板
document.getElementById('btnCopy').addEventListener('click', async () => {
    const btn = document.getElementById('btnCopy');

    await chrome.runtime.sendMessage({
        type: 'copy-to-clipboard',
        text: currentCommand || currentUrl
    });

    // 通知后台删除拦截记录
    await chrome.runtime.sendMessage({
        type: 'cancel-intercept',
        interceptId: interceptId
    });

    // 更新按钮状态
    btn.textContent = '✓ 已复制';
    btn.classList.add('copied');

    setTimeout(() => window.close(), 500);
});

// 使用浏览器下载（重新创建下载）
document.getElementById('btnDownload').addEventListener('click', async () => {
    await chrome.runtime.sendMessage({
        type: 'start-download',
        interceptId: interceptId
    });
    window.close();
});
