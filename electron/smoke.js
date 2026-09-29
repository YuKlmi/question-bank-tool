/**
 * 端到端冒烟测试（真实 Electron 环境）。
 *
 * 验证的是**整条链路**：渲染进程 → preload → IPC → 主进程 → Python 引擎 → 返回。
 * 单元测试覆盖不到这一段，而它恰恰是最容易在打包后才暴露问题的部分。
 *
 * 运行：npm run test:e2e
 * 退出码 0 表示全部通过。
 */
const { app, BrowserWindow, protocol } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const { PyBridge } = require('./pybridge');

const REPO_ROOT = path.resolve(__dirname, '..');
const DATA_DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'qtb-smoke-'));
const MEDIA_DIR = path.join(DATA_DIR, 'media');

protocol.registerSchemesAsPrivileged([
  {
    scheme: 'qtb-media',
    privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
  },
]);

let bridge = null;
const results = [];
const consoleErrors = [];

function record(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  → ' + detail : ''}`);
}

function registerMediaProtocol() {
  protocol.handle('qtb-media', (request) => {
    const url = new URL(request.url);
    const rel = decodeURIComponent(url.pathname).replace(/^\/+/, '');
    const target = path.resolve(MEDIA_DIR, rel);
    if (!target.startsWith(path.resolve(MEDIA_DIR)) || !fs.existsSync(target)) {
      return new Response('not found', { status: 404 });
    }
    return new Response(fs.readFileSync(target));
  });
}

async function run() {
  fs.mkdirSync(MEDIA_DIR, { recursive: true });
  registerMediaProtocol();

  bridge = new PyBridge({
    repoRoot: REPO_ROOT,
    resourcesPath: app.isPackaged ? process.resourcesPath : null,
    dataDir: DATA_DIR,
    logger: () => {},
  });

  const win = new BrowserWindow({
    show: false,
    width: 1400,
    height: 900,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  const ipc = require('electron').ipcMain;
  ipc.handle('qtb:call', async (_e, method, params) => {
    try {
      return { ok: true, result: await bridge.call(method, params || {}) };
    } catch (err) {
      return { ok: false, error: { message: err.message, type: err.type } };
    }
  });
  ipc.handle('qtb:mediaUrl', (_e, rel) => `qtb-media://local/${rel}`);
  ipc.handle('qtb:pickFile', async () => []);
  ipc.handle('qtb:pickSavePath', async () => null);
  ipc.handle('qtb:pickDirectory', async () => null);
  ipc.handle('qtb:openPath', async () => true);
  ipc.handle('qtb:showItem', async () => true);
  ipc.handle('qtb:revealDataDir', async () => true);

  win.webContents.on('console-message', (_e, level, message) => {
    // level 3 = error
    if (level >= 3) consoleErrors.push(message);
  });

  const distIndex = path.join(REPO_ROOT, 'dist', 'index.html');
  if (!fs.existsSync(distIndex)) {
    record('前端产物存在', false, 'dist/index.html 不存在，请先 npm run build');
    return;
  }
  record('前端产物存在', true);

  await win.loadFile(distIndex);
  await new Promise((r) => setTimeout(r, 1500));

  const evaluate = (code) => win.webContents.executeJavaScript(code, true);

  // 1) preload 桥是否暴露
  const hasBridge = await evaluate('typeof window.qtb === "object" && typeof window.qtb.call === "function"');
  record('preload 安全桥已暴露', hasBridge);

  // 2) 通过桥调用引擎
  const ping = await evaluate('window.qtb.call("system.ping").then(r => JSON.stringify(r))');
  record('渲染进程可调用引擎 (system.ping)', ping.includes('"pong":true'), ping);

  // 3) 模板列表（验证真实业务数据能过来）
  const tpl = await evaluate('window.qtb.call("system.info").then(r => r.templates.length)');
  record('引擎返回模板列表', tpl >= 2, `templates=${tpl}`);

  // 4) Vue 应用是否挂载
  const mounted = await evaluate('document.querySelector("#app").children.length > 0');
  record('Vue 应用已挂载', mounted);

  // 5) 侧边栏与文档库界面渲染
  const navText = await evaluate('document.querySelector(".qtb-sidebar")?.innerText || ""');
  record(
    '文档库界面渲染（侧边栏可见）',
    navText.includes('文档库') && navText.includes('错题本'),
    navText.replace(/\s+/g, ' ').slice(0, 60),
  );

  // 6) 初始化没有报错（有报错会显示 el-result 错误页）
  const initOk = await evaluate('!document.querySelector(".el-result")');
  record('应用初始化无错误', initOk);

  // 7) 导入文档 → 题目数据能到前端（走完整链路）
  const pdfSample = path.join(REPO_ROOT, 'samples', '行测题库及答案详解二.pdf');
  if (fs.existsSync(pdfSample)) {
    const imported = await evaluate(`
      window.qtb.call("doc.import", { path: ${JSON.stringify(pdfSample)} })
        .then(d => JSON.stringify({ n: d.question_count, a: d.answered_count, p: d.pending_input }))
    `);
    const parsed = JSON.parse(imported);
    record(
      '通过桌面壳导入 PDF 并解析',
      parsed.n === 135 && parsed.a === 134 && parsed.p === 7,
      JSON.stringify(parsed),
    );

    const listRes = await evaluate(`
      window.qtb.call("question.list", { docId: 1, filters: { pageSize: 5 } })
        .then(r => JSON.stringify({ total: r.total, got: r.items.length }))
    `);
    const listed = JSON.parse(listRes);
    record('题目列表可查询', listed.total === 135 && listed.got === 5, listRes);
  } else {
    record('通过桌面壳导入 PDF 并解析', false, '样例文件缺失');
  }

  record('渲染进程无未捕获错误', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
}

app.whenReady().then(async () => {
  try {
    await run();
  } catch (err) {
    record('冒烟测试执行', false, err.message);
    console.error(err);
  } finally {
    const failed = results.filter((r) => !r.ok);
    console.log(`\n冒烟测试：${results.length - failed.length}/${results.length} 通过`);
    if (bridge) bridge.close();
    try {
      fs.rmSync(DATA_DIR, { recursive: true, force: true });
    } catch {
      /* 清理失败不影响结果 */
    }
    app.exit(failed.length === 0 ? 0 : 1);
  }
});

app.on('window-all-closed', () => {});
