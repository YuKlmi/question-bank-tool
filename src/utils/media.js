/**
 * 媒体路径工具。
 *
 * 渲染进程用自定义协议 qtb-media:// 加载图片，规则必须与 electron/main.js
 * 的 protocol.handle 保持一致。这里是同步的，模板里可以直接用，
 * 不必为每个 <img> 走一次 IPC。
 */
export function mediaUrl(relPath) {
  if (!relPath) return '';
  const normalized = String(relPath).replace(/\\/g, '/').replace(/^\/+/, '');
  const encoded = normalized.split('/').map(encodeURIComponent).join('/');
  return `qtb-media://local/${encoded}`;
}

export default mediaUrl;
