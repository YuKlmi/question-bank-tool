/**
 * 开发启动器：先起 Vite dev server，等端口就绪后再拉起 Electron。
 *
 * 之所以自己写而不是用 concurrently，是为了确保 Electron 一定在
 * 渲染服务可用之后才启动，避免白屏。
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 5173;
const HOST = '127.0.0.1';
const URL = `http://localhost:${PORT}`;

const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';

function waitForPort(port, host, timeoutMs = 60000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.connect({ port, host });
      socket.once('connect', () => {
        socket.destroy();
        resolve();
      });
      socket.once('error', () => {
        socket.destroy();
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`等待 Vite (${host}:${port}) 超时`));
        } else {
          setTimeout(attempt, 300);
        }
      });
    };
    attempt();
  });
}

const vite = spawn(npmCmd, ['run', 'dev:renderer', '--silent'], {
  cwd: ROOT,
  stdio: ['ignore', 'inherit', 'inherit'],
  shell: process.platform === 'win32',
});

let electron = null;

function shutdown(code = 0) {
  if (electron && !electron.killed) electron.kill();
  if (vite && !vite.killed) vite.kill();
  process.exit(code);
}

process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));

try {
  await waitForPort(PORT, HOST);
  console.log(`\n[dev] 渲染服务已就绪：${URL}\n[dev] 启动 Electron…\n`);

  electron = spawn(npmCmd, ['exec', '--', 'electron', '.'], {
    cwd: ROOT,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env: { ...process.env, QTB_DEV: '1', QTB_DEV_URL: URL },
  });

  electron.on('exit', (code) => shutdown(code ?? 0));
} catch (err) {
  console.error('[dev] 启动失败:', err.message);
  shutdown(1);
}
