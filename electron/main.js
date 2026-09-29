/**
 * Electron 主进程。
 *
 * 职责边界很清晰：
 *   - 渲染进程只负责界面，所有业务都通过 IPC 转发给 Python 引擎
 *   - 数据库、解析、导出全部在 Python 侧，主进程不做业务逻辑
 *   - 图片通过自定义协议 qtb-media:// 提供，避免在渲染进程暴露文件系统
 */
const { app, BrowserWindow, dialog, ipcMain, protocol, shell } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');

const { PyBridge } = require('./pybridge');

const REPO_ROOT = path.resolve(__dirname, '..');
const DEV_URL = process.env.QTB_DEV_URL || 'http://localhost:5173';
const IS_DEV = process.env.QTB_DEV === '1' || !!process.env.QTB_DEV_URL;

/** 数据目录：默认放「我的文档/题库数据」，可通过环境变量覆盖。 */
function resolveDataDir() {
  if (process.env.QTB_DATA_DIR) return process.env.QTB_DATA_DIR;
  try {
    return path.join(app.getPath('documents'), '题库数据');
  } catch {
    return path.join(REPO_ROOT, 'data');
  }
}

const DATA_DIR = resolveDataDir();
const MEDIA_DIR = path.join(DATA_DIR, 'media');

let mainWindow = null;
let bridge = null;

// 图片协议需要在 app ready 之前声明为特权协议
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'qtb-media',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
  },
]);

function logToFile(...args) {
  const line = `[${new Date().toISOString()}] ${args.join(' ')}\n`;
  process.stdout.write(line);
  try {
    fs.appendFileSync(path.join(DATA_DIR, 'app.log'), line);
  } catch {
    /* 日志失败不影响主流程 */
  }
}

function registerMediaProtocol() {
  protocol.handle('qtb-media', (request) => {
    try {
      const url = new URL(request.url);
      // qtb-media://local/<relative path>
      const rel = decodeURIComponent(url.pathname).replace(/^\/+/, '');
      const target = path.resolve(MEDIA_DIR, rel);
      // 防目录穿越：解析后必须仍在 media 目录内
      if (!target.startsWith(path.resolve(MEDIA_DIR))) {
        return new Response('forbidden', { status: 403 });
      }
      if (!fs.existsSync(target)) {
        return new Response('not found', { status: 404 });
      }
      return new Response(fs.readFileSync(target), {
        headers: { 'content-type': contentTypeOf(target) },
      });
    } catch (err) {
      logToFile('媒体协议出错:', err.message);
      return new Response('error', { status: 500 });
    }
  });
}

function contentTypeOf(file) {
  const ext = path.extname(file).toLowerCase();
  return {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp',
    '.webp': 'image/webp',
    '.tif': 'image/tiff',
    '.tiff': 'image/tiff',
  }[ext] || 'application/octet-stream';
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1100,
    minHeight: 700,
    title: '题库存取练习工具',
    backgroundColor: '#f5f7fa',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  if (IS_DEV) {
    mainWindow.loadURL(DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadFile(path.join(REPO_ROOT, 'dist', 'index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // 外部链接交给系统浏览器，不在应用内打开
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
}

function registerIpc() {
  // 统一的引擎调用通道
  ipcMain.handle('qtb:call', async (_event, method, params) => {
    try {
      const result = await bridge.call(method, params || {});
      return { ok: true, result };
    } catch (err) {
      logToFile(`IPC ${method} 失败:`, err.message);
      return { ok: false, error: { message: err.message, type: err.type } };
    }
  });

  ipcMain.handle('qtb:pickFile', async () => {
    const res = await dialog.showOpenDialog(mainWindow, {
      title: '选择题库文档',
      properties: ['openFile', 'multiSelections'],
      filters: [
        { name: '题库文档', extensions: ['doc', 'docx', 'pdf'] },
        { name: '全部文件', extensions: ['*'] },
      ],
    });
    return res.canceled ? [] : res.filePaths;
  });

  ipcMain.handle('qtb:pickSavePath', async (_e, { defaultName, filters }) => {
    const res = await dialog.showSaveDialog(mainWindow, {
      defaultPath: defaultName,
      filters: filters || [{ name: '全部文件', extensions: ['*'] }],
    });
    return res.canceled ? null : res.filePath;
  });

  ipcMain.handle('qtb:pickDirectory', async () => {
    const res = await dialog.showOpenDialog(mainWindow, {
      title: '选择目录',
      properties: ['openDirectory', 'createDirectory'],
    });
    return res.canceled ? null : res.filePaths[0];
  });

  ipcMain.handle('qtb:openPath', async (_e, target) => {
    if (!target) return false;
    return shell.openPath(target);
  });

  ipcMain.handle('qtb:showItem', async (_e, target) => {
    if (!target) return false;
    shell.showItemInFolder(target);
    return true;
  });

  ipcMain.handle('qtb:revealDataDir', async () => {
    await shell.openPath(DATA_DIR);
    return true;
  });

  // 便于渲染进程把相对媒体路径拼成可加载 URL（不暴露绝对路径）
  ipcMain.handle('qtb:mediaUrl', (_e, relPath) => {
    if (!relPath) return null;
    const normalized = String(relPath).replace(/\\/g, '/').replace(/^\/+/, '');
    return `qtb-media://local/${normalized.split('/').map(encodeURIComponent).join('/')}`;
  });
}

app.whenReady().then(() => {
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  registerMediaProtocol();

  bridge = new PyBridge({
    repoRoot: REPO_ROOT,
    resourcesPath: process.resourcesPath && app.isPackaged ? process.resourcesPath : null,
    dataDir: DATA_DIR,
    logger: (...args) => logToFile('[py]', ...args),
  });

  registerIpc();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (bridge) bridge.close();
  if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
  if (bridge) bridge.close();
});

module.exports = { resolveDataDir };
