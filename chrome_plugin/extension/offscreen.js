/**
 * Offscreen 文档 - 用于剪贴板操作
 */

chrome.runtime.onMessage.addListener((message) => {
    if (message.target !== 'offscreen') return;

    if (message.type === 'copy') {
        copyTextToClipboard(message.text);
    }
});

function copyTextToClipboard(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    document.body.appendChild(textarea);
    textarea.select();

    try {
        document.execCommand('copy');
        console.log('[Offscreen] 复制成功:', text);
    } catch (err) {
        console.error('[Offscreen] 复制失败:', err);
    }

    document.body.removeChild(textarea);
}
