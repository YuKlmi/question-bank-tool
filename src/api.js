/**
 * 与解析引擎的接口封装。
 *
 * 引擎方法名即后端契约（见 engine/rpc.py 的 build_routes）。
 * 所有命名统一 snake_case，与数据库字段保持一致，避免多一层转换。
 */

function bridge() {
  if (typeof window === 'undefined' || !window.qtb) {
    throw new Error(
      '未检测到桌面运行环境。请通过 Electron 启动（npm run dev / npm start），不要直接用浏览器打开。',
    );
  }
  return window.qtb;
}

/**
 * 把参数转成纯对象再交给 preload。
 *
 * 必须在这里做，不能只在 preload 里做：Pinia 的 state（如 filters）是
 * Vue 响应式 Proxy，而 contextBridge 跨「主世界 → 隔离世界」时用的是
 * 结构化克隆，**Proxy 无法克隆**，会直接抛 "An object could not be cloned."，
 * 那时 preload 里的清洗代码根本没机会执行。
 */
function toPlain(value) {
  if (value === undefined || value === null) return {};
  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return {};
  }
}

const call = (method, params) => bridge().call(method, toPlain(params));

export const api = {
  // 系统
  ping: () => call('system.ping'),
  info: () => call('system.info'),
  paths: () => call('system.paths'),

  // 文档（最外层容器）
  importDocument: (filePath, templateId) =>
    call('doc.import', { path: filePath, templateId }),
  listDocuments: () => call('doc.list'),
  getDocument: (docId) => call('doc.get', { docId }),
  deleteDocument: (docId, purgeMedia = false) =>
    call('doc.delete', { docId, purgeMedia }),
  reparseDocument: (docId, templateId) =>
    call('doc.reparse', { docId, templateId }),
  docStats: (docId) => call('doc.stats', { docId }),
  docGroups: (docId) => call('doc.groups', { docId }),

  // 题目
  listQuestions: (docId, filters) => call('question.list', { docId, filters }),
  getQuestion: (questionId) => call('question.get', { questionId }),
  updateQuestion: (questionId, fields) =>
    call('question.update', { questionId, fields }),
  createQuestion: (docId, payload) => call('question.create', { docId, payload }),
  deleteQuestion: (questionId) => call('question.delete', { questionId }),
  setAnswer: (questionId, answer) => call('question.setAnswer', { questionId, answer }),

  // 答题
  practicePick: (docId, mode, filters, limit) =>
    call('practice.pick', { docId, mode, filters, limit }),
  practiceSubmit: (questionId, userAnswer, durationMs) =>
    call('practice.submit', { questionId, userAnswer, durationMs }),
  selfAssess: (questionId, level) =>
    call('practice.selfAssess', { questionId, level }),

  // 错题本 / 收藏
  listWrongbook: (docId, page = 1, pageSize = 50) =>
    call('wrongbook.list', { docId, page, pageSize }),
  setWrongbook: (questionId, inBook) =>
    call('wrongbook.set', { questionId, inBook }),
  toggleStar: (questionId) => call('review.star', { questionId }),
  setTags: (questionId, tags) => call('review.tags', { questionId, tags }),
  getReview: (questionId) => call('review.get', { questionId }),
  listStarred: (docId, page = 1, pageSize = 50, tag = null) =>
    call('review.listStarred', { docId, page, pageSize, tag }),
  allTags: () => call('review.allTags'),

  // 批注
  listAnnotations: (questionId) => call('annotation.list', { questionId }),
  createAnnotation: (questionId, content, type, color, anchor) =>
    call('annotation.create', { questionId, content, type, color, anchor }),
  updateAnnotation: (annotationId, content, color) =>
    call('annotation.update', { annotationId, content, color }),
  deleteAnnotation: (annotationId) => call('annotation.delete', { annotationId }),

  // 图片
  listImages: (docId, unassignedOnly = false) =>
    call('image.list', { docId, unassignedOnly }),

  // 导出
  exportMarkdown: (docId, outPath) => call('export.markdown', { docId, outPath }),
  exportCsv: (docId, outPath) => call('export.csv', { docId, outPath }),

  // 设置 / 备份
  getSettings: () => call('settings.get'),
  updateSettings: (patch) => call('settings.update', { patch }),
  createBackup: () => call('backup.create'),
  listBackups: () => call('backup.list'),
  restoreBackup: (backupPath) => call('backup.restore', { backupPath }),

  // 桌面能力
  pickFile: () => bridge().pickFile(),
  pickSavePath: (options) => bridge().pickSavePath(options),
  pickDirectory: () => bridge().pickDirectory(),
  openPath: (target) => bridge().openPath(target),
  showItem: (target) => bridge().showItem(target),
  revealDataDir: () => bridge().revealDataDir(),
  // 注：图片 URL 由 src/utils/media.js 同步拼装，不走 IPC
};

export default api;
