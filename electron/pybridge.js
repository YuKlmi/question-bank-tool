/**
 * Python 解析引擎的 JSON-RPC 客户端。
 *
 * 主进程通过子进程拉起 engine.rpc，用行分隔 JSON 通信。
 * 之所以把数据库与解析都放在 Python 侧，是为了彻底避开 Node 原生模块
 * （better-sqlite3 之类）在 Electron 下的 ABI 编译问题。
 */
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const readline = require('node:readline');

/** 解析引擎启动命令：打包后用 PyInstaller 产物，开发时用本机 python。 */
function resolveEngineCommand(repoRoot, resourcesPath) {
  const isPackaged = !!resourcesPath;
  if (isPackaged) {
    const exe = path.join(resourcesPath, 'engine', 'qtb-engine.exe');
    if (fs.existsSync(exe)) return { cmd: exe, args: [], cwd: path.dirname(exe) };
    const py = path.join(resourcesPath, 'engine', 'engine');
    if (fs.existsSync(py)) {
      return { cmd: 'python', args: ['-m', 'engine.rpc'], cwd: path.dirname(py) };
    }
  }
  return { cmd: 'python', args: ['-m', 'engine.rpc'], cwd: repoRoot };
}

class PyBridge {
  constructor({ repoRoot, resourcesPath, dataDir, logger }) {
    const { cmd, args, cwd } = resolveEngineCommand(repoRoot, resourcesPath);
    this.logger = logger || ((...a) => console.log('[py]', ...a));
    this.pending = new Map();
    this.seq = 0;
    this.ready = false;
    this.closed = false;

    const fullArgs = [...args, '--data-dir', dataDir];
    this.logger('启动解析引擎:', cmd, fullArgs.join(' '), 'cwd=' + cwd);

    this.proc = spawn(cmd, fullArgs, {
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });

    this.proc.on('error', (err) => {
      this.logger('引擎启动失败:', err.message);
      this._failAll(new Error(`无法启动解析引擎：${err.message}`));
    });
    this.proc.on('exit', (code, signal) => {
      this.closed = true;
      this.logger(`引擎退出 code=${code} signal=${signal}`);
      this._failAll(new Error(`解析引擎已退出（code=${code}）`));
    });

    // stdout 只承载协议，逐行解析
    const rl = readline.createInterface({ input: this.proc.stdout });
    rl.on('line', (line) => this._onLine(line));

    // stderr 是日志
    const errRl = readline.createInterface({ input: this.proc.stderr });
    errRl.on('line', (line) => this.logger('[engine]', line));

    this.ready = true;
  }

  _onLine(line) {
    const text = line.trim();
    if (!text) return;
    let msg;
    try {
      msg = JSON.parse(text);
    } catch {
      this.logger('无法解析引擎输出:', text.slice(0, 200));
      return;
    }
    const batch = Array.isArray(msg) ? msg : [msg];
    for (const item of batch) {
      const waiter = this.pending.get(item.id);
      if (!waiter) continue;
      this.pending.delete(item.id);
      if (item.ok) waiter.resolve(item.result);
      else {
        const err = new Error(item.error?.message || '引擎调用失败');
        err.type = item.error?.type;
        waiter.reject(err);
      }
    }
  }

  _failAll(err) {
    for (const [, waiter] of this.pending) waiter.reject(err);
    this.pending.clear();
  }

  /** 调用引擎方法，返回 Promise。 */
  call(method, params = {}) {
    if (this.closed) {
      return Promise.reject(new Error('解析引擎未运行'));
    }
    const id = ++this.seq;
    const payload = JSON.stringify({ id, method, params });
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      try {
        this.proc.stdin.write(payload + '\n');
      } catch (e) {
        this.pending.delete(id);
        reject(e);
      }
    });
  }

  close() {
    this.closed = true;
    try {
      this.proc.stdin.end();
      this.proc.kill();
    } catch {
      /* 忽略关闭异常 */
    }
  }
}

module.exports = { PyBridge, resolveEngineCommand };
