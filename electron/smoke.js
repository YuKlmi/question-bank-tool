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

    // 8) 真实操作「浏览与校对」界面：进入、展开题目、看正文是否渲染
    await evaluate(`location.hash = "#/doc/1/questions"`);
    await new Promise((r) => setTimeout(r, 2500));

    const listCount = await evaluate(
      'document.querySelectorAll(".qtb-question-item").length',
    );
    record('浏览与校对：题目列表渲染', listCount > 0, `item 数=${listCount}`);

    if (listCount === 0) {
      // 出问题时把上下文打出来，方便定位是哪一环断的
      const diag = await evaluate(`
        JSON.stringify({
          hash: location.hash,
          header: (document.querySelector(".qtb-header")?.innerText || "").slice(0, 120),
          contentText: (document.querySelector(".qtb-content")?.innerText || "").slice(0, 200),
          bodyTail: (document.body.innerText || "").slice(-200),
          hasErrorResult: !!document.querySelector(".el-result"),
        })
      `);
      record('浏览与校对：诊断信息', false, diag);

      const direct = await evaluate(`
        (async () => {
          const out = {};
          try { out.docGet = (await window.qtb.call("doc.get", { docId: 1 })).name; }
          catch (e) { out.docGet = "ERR " + e.message; }
          try { out.groups = (await window.qtb.call("doc.groups", { docId: 1 })).length; }
          catch (e) { out.groups = "ERR " + e.message; }
          try {
            const r = await window.qtb.call("question.list", {
              docId: 1,
              filters: { groupSeq: null, reviewState: null, type: null,
                         hasAnswer: null, keyword: "", page: 1, pageSize: 20 },
            });
            out.list = r.total + "/" + r.items.length;
          } catch (e) { out.list = "ERR " + e.message; }
          return JSON.stringify(out);
        })()
      `);
      record('浏览与校对：各接口直连结果', false, direct);
    }

    // 展开第一题
    const clicked = await evaluate(`
      (() => {
        const head = document.querySelector(".qtb-question-head");
        if (!head) return false;
        head.click();
        return true;
      })()
    `);
    record('浏览与校对：题目可点击展开', clicked === true);

    await new Promise((r) => setTimeout(r, 2000));
    const bodyInfo = await evaluate(`
      JSON.stringify((() => {
        const body = document.querySelector(".qtb-question-body");
        if (!body) return { found: false };
        const stem = body.querySelector(".qtb-stem");
        const imgs = body.querySelectorAll(".qtb-image");
        return {
          found: true,
          textLen: (body.innerText || "").trim().length,
          hasStem: !!stem,
          imageCount: imgs.length,
        };
      })())
    `);
    const bi = JSON.parse(bodyInfo);
    // 首题是图片题（无文本题干），因此「有题干」或「有原图」二者其一即可
    record(
      '浏览与校对：展开后题目正文可见',
      bi.found && (bi.hasStem || bi.imageCount > 0) && bi.textLen > 20,
      bodyInfo,
    );

    // 9) 答题页：上/下一题可自由切换（不需要先提交）
    await evaluate(`location.hash = "#/doc/1/practice"`);
    await new Promise((r) => setTimeout(r, 1500));

    // 先点「开始练习」抽题
    const started = await evaluate(`
      (() => {
        const btn = [...document.querySelectorAll("button")].find(b => b.innerText.trim() === "开始练习");
        if (!btn) return false;
        btn.click();
        return true;
      })()
    `);
    record('答题页：可开始练习', started === true);
    await new Promise((r) => setTimeout(r, 2000));

    // 默认抽题量应为该文档已识别的全部题目（此卷 135 题），不再是固定 20
    const pickedTotal = await evaluate(`
      (() => {
        const txt = document.querySelector(".qtb-content")?.innerText || "";
        const m = txt.match(/第 \\d+ \\/ (\\d+) 题/);
        return m ? m[1] : "no-indicator";
      })()
    `);
    record('答题页：默认抽满该文档全部题目', pickedTotal === '135', `抽到 ${pickedTotal} 题`);

    const practiceBtns = await evaluate(`
      JSON.stringify([...document.querySelectorAll(".qtb-panel button")].map(b => b.innerText.trim()))
    `);
    record(
      '答题页：存在上/下一题按钮',
      practiceBtns.includes('上一题') && practiceBtns.includes('下一题'),
      practiceBtns,
    );

    // 直接点「下一题」切到第 2 题，验证无需提交也能翻页
    const navWorked = await evaluate(`
      (async () => {
        const btn = [...document.querySelectorAll("button")].find(b => b.innerText.trim().startsWith("下一题"));
        if (!btn) return "no-button";
        btn.click();
        await new Promise(r => setTimeout(r, 400));
        const txt = document.querySelector(".qtb-content")?.innerText || "";
        const m = txt.match(/第 (\\d+) \\/ (\\d+) 题/);
        return m ? m[1] : "no-indicator";
      })()
    `);
    record('答题页：下一题可直接翻页', navWorked === '2', `当前题序号=${navWorked}`);

    // 10) 答题页：答案与解析默认隐藏，点「查看解析」才展开
    const revealRaw = await evaluate(`
      (async () => {
        const wait = (ms) => new Promise(r => setTimeout(r, ms));
        // 先翻到一道有文字选项的题（首题可能是图片题面，没有可点的选项）
        let hasOption = false;
        for (let i = 0; i < 12 && !hasOption; i++) {
          if (document.querySelector(".qtb-option")) { hasOption = true; break; }
          const next = [...document.querySelectorAll("button")]
            .find(b => b.innerText.trim().startsWith("下一题"));
          if (!next) break;
          next.click();
          await wait(400);
        }
        if (!hasOption) return JSON.stringify({ step: "no-option-question" });

        document.querySelector(".qtb-option").click();
        await wait(200);
        const submitBtn = [...document.querySelectorAll("button")]
          .find(b => b.innerText.trim().startsWith("提交并对照答案"));
        if (!submitBtn) return JSON.stringify({ step: "no-submit-button" });
        submitBtn.click();
        await wait(1500);

        const beforeAnswer = !!document.querySelector(".qtb-answer-box");
        const beforeExplain = !!document.querySelector(".qtb-explain-box");
        const revealBtn = [...document.querySelectorAll("button")]
          .find(b => b.innerText.trim() === "查看解析");
        if (!revealBtn) {
          return JSON.stringify({ step: "no-reveal-button", beforeAnswer, beforeExplain });
        }
        revealBtn.click();
        await wait(600);
        return JSON.stringify({
          beforeAnswer,
          beforeExplain,
          afterAnswer: !!document.querySelector(".qtb-answer-box"),
          afterExplain: !!document.querySelector(".qtb-explain-box"),
        });
      })()
    `);
    let reveal = {};
    try { reveal = JSON.parse(revealRaw); } catch { reveal = { step: 'unparsable' }; }
    record(
      '答题页：答案与解析默认隐藏，点「查看解析」才展开',
      reveal.beforeAnswer === false && reveal.beforeExplain === false && reveal.afterAnswer === true,
      revealRaw,
    );

    // 11) 答题进度按文档保存：切走再回来，题位与已作答状态应原样恢复
    const readState = `
      (() => {
        const txt = document.querySelector(".qtb-content")?.innerText || "";
        const cursor = txt.match(/第 (\\d+) \\/ (\\d+) 题/);
        const answered = txt.match(/已作答 (\\d+) \\/ (\\d+)/);
        return JSON.stringify({
          cursor: cursor ? cursor[1] : "none",
          answered: answered ? answered[1] : "none",
          restoredTag: txt.includes("已恢复上次进度"),
        });
      })()
    `;
    const before = await evaluate(readState);
    await new Promise((r) => setTimeout(r, 1200));   // 等防抖保存落库

    await evaluate(`location.hash = "#/doc/1/questions"`);
    await new Promise((r) => setTimeout(r, 1200));
    await evaluate(`location.hash = "#/doc/1/practice"`);
    await new Promise((r) => setTimeout(r, 2500));

    const after = await evaluate(readState);
    const b = JSON.parse(before);
    const a = JSON.parse(after);
    record(
      '答题进度：切走再回来可恢复题位与已作答数',
      a.cursor === b.cursor && a.answered === b.answered && a.restoredTag === true,
      `离开前 ${before} → 回来后 ${after}`,
    );
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
