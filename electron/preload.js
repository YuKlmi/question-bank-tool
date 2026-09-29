/**
 * 渲染进程与主进程之间的安全桥。
 *
 * 只暴露必要的几个方法，渲染进程完全拿不到 Node / 文件系统能力。
 */
const { contextBridge, ipcRenderer } = require('electron');

/**
 * 把参数清洗成可结构化克隆的纯对象。
 *
 * 渲染进程传进来的往往是 Vue 响应式 Proxy（如 Pinia 里的 filters），
 * 而 IPC 用的是结构化克隆算法，**Proxy 无法克隆**，会直接抛
 * "An object could not be cloned."。这里统一过一遍 JSON 序列化，
 * 既清掉 Proxy，也顺便去掉函数等不可传输的值。
 */
function sanitize(value) {
  if (value === undefined || value === null) return {};
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return {};
  }
}

contextBridge.exposeInMainWorld('qtb', {
  /** 调用解析引擎（唯一的业务通道）。失败会 reject，带 message / type。 */
  async call(method, params) {
    const resp = await ipcRenderer.invoke('qtb:call', method, sanitize(params));
    if (!resp || resp.ok !== true) {
      const err = new Error(resp?.error?.message || '引擎调用失败');
      err.type = resp?.error?.type;
      throw err;
    }
    return resp.result;
  },

  /** 选择题库文档，返回绝对路径数组。 */
  pickFile: () => ipcRenderer.invoke('qtb:pickFile'),

  /** 选择保存位置，取消返回 null。 */
  pickSavePath: (options) => ipcRenderer.invoke('qtb:pickSavePath', options || {}),

  /** 选择目录。 */
  pickDirectory: () => ipcRenderer.invoke('qtb:pickDirectory'),

  /** 用系统默认程序打开文件/目录。 */
  openPath: (target) => ipcRenderer.invoke('qtb:openPath', target),

  /** 在资源管理器中定位文件。 */
  showItem: (target) => ipcRenderer.invoke('qtb:showItem', target),

  /** 打开数据目录。 */
  revealDataDir: () => ipcRenderer.invoke('qtb:revealDataDir'),

  /** 把媒体相对路径转成可加载的 URL（不暴露绝对路径）。 */
  mediaUrl: (relPath) => ipcRenderer.invoke('qtb:mediaUrl', relPath),
});
