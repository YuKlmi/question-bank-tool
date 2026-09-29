/**
 * 桌面壳 ↔ 解析引擎 的集成测试。
 *
 * 这是整个应用最容易出问题、也最难靠肉眼发现的接缝：
 * Python 子进程的启动、行分隔 JSON 协议的收发、错误透传。
 * 用 Node 内置测试运行器，不需要额外依赖：
 *     npm test
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { PyBridge } from '../../electron/pybridge.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const SAMPLES = path.join(ROOT, 'samples');
const PDF_SAMPLE = path.join(SAMPLES, '行测题库及答案详解二.pdf');

function makeBridge(t) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'qtb-test-'));
  const logs = [];
  const bridge = new PyBridge({
    repoRoot: ROOT,
    resourcesPath: null,
    dataDir,
    logger: (...args) => logs.push(args.join(' ')),
  });
  t.after(() => bridge.close());
  return { bridge, dataDir, logs };
}

test('引擎可以通过 JSON-RPC 正常响应', async (t) => {
  const { bridge } = makeBridge(t);
  const pong = await bridge.call('system.ping');
  assert.deepEqual(pong, { pong: true });
});

test('system.info 返回数据路径与模板列表', async (t) => {
  const { bridge, dataDir } = makeBridge(t);
  const info = await bridge.call('system.info');

  assert.ok(info.paths.data_dir, '应返回数据目录');
  assert.ok(info.paths.data_dir.includes(path.basename(dataDir)) || info.paths.data_dir === dataDir);

  const ids = info.templates.map((x) => x.id);
  assert.ok(ids.includes('pdf-consolidated'));
  assert.ok(ids.includes('docx-mixed'));
});

test('未知方法返回结构化错误而不是崩溃', async (t) => {
  const { bridge } = makeBridge(t);
  await assert.rejects(
    () => bridge.call('no.such.method'),
    (err) => {
      assert.equal(err.type, 'MethodNotFound');
      return true;
    },
  );
  // 出错后引擎仍然可用
  assert.deepEqual(await bridge.call('system.ping'), { pong: true });
});

test('并发调用不会串号', async (t) => {
  const { bridge } = makeBridge(t);
  const results = await Promise.all([
    bridge.call('system.ping'),
    bridge.call('doc.list'),
    bridge.call('system.paths'),
    bridge.call('settings.get'),
    bridge.call('backup.list'),
  ]);
  assert.deepEqual(results[0], { pong: true });
  assert.deepEqual(results[1], []);
  assert.ok(Array.isArray(results[4]));
});

test('导入 PDF 全流程：解析 → 入库 → 查询 → 备份', async (t) => {
  if (!fs.existsSync(PDF_SAMPLE)) {
    t.skip('样例文件缺失，跳过');
    return;
  }

  const { bridge } = makeBridge(t);

  const doc = await bridge.call('doc.import', { path: PDF_SAMPLE });
  assert.equal(doc.question_count, 135);
  assert.equal(doc.answered_count, 134);
  assert.equal(doc.pending_input, 7);

  const list = await bridge.call('question.list', {
    docId: doc.id,
    filters: { pageSize: 10 },
  });
  assert.equal(list.total, 135);
  assert.equal(list.items.length, 10);

  const first = await bridge.call('question.get', { questionId: list.items[0].id });
  assert.ok(Array.isArray(first.options));
  assert.ok(first.review);

  const backup = await bridge.call('backup.create', {});
  assert.ok(fs.existsSync(backup.path));

  const backups = await bridge.call('backup.list', {});
  assert.ok(backups.some((b) => b.name === backup.name));
});

test('引擎退出后调用会给出明确错误', async (t) => {
  const { bridge } = makeBridge(t);
  await bridge.call('system.ping');
  bridge.close();
  await assert.rejects(
    () => bridge.call('system.ping'),
    /未运行|已退出/,
  );
});
