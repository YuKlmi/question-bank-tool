/**
 * 把 Python 解析引擎打成单文件 exe，供 Electron 打包时作为 extraResources 带上。
 *
 * 之所以脚本化而不是写死在 npm script 里：PyInstaller 的 --add-data
 * 源路径是相对 spec 文件目录解析的，必须传绝对路径，命令行里不好写。
 *
 * 用法：node scripts/pack-engine.mjs
 * 产物：engine/dist/qtb-engine.exe
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const TEMPLATES = path.join(ROOT, 'engine', 'templates');
const ENTRY = path.join('engine', 'pack_entry.py');
const OUT = path.join('engine', 'dist');
const WORK = path.join('.cache', 'pyinstaller');

if (!fs.existsSync(TEMPLATES)) {
  console.error(`模板目录不存在：${TEMPLATES}`);
  process.exit(1);
}

const args = [
  '-m', 'PyInstaller',
  '--onefile',
  '--noconfirm',
  '--name', 'qtb-engine',
  '--paths', ROOT,
  // 注意：源路径必须绝对，落点用正斜杠（Windows 上分隔符是 ; ）
  '--add-data', `${TEMPLATES};engine/templates`,
  // pywin32 的 COM 组件是动态导入的，PyInstaller 扫不到
  '--hidden-import', 'win32com.client',
  '--hidden-import', 'pythoncom',
  // python-docx 自带默认模板、pymupdf 自带二进制资源
  '--collect-data', 'docx',
  '--collect-data', 'pymupdf',
  '--distpath', OUT,
  '--workpath', WORK,
  '--specpath', WORK,
  ENTRY,
];

console.log('[pack] PyInstaller 开始打包解析引擎…');
const r = spawnSync('python', args, { cwd: ROOT, stdio: 'inherit' });

if (r.status !== 0) {
  console.error('\n[pack] 引擎打包失败。请确认已安装 pyinstaller：python -m pip install pyinstaller');
  process.exit(r.status ?? 1);
}

const exe = path.join(ROOT, OUT, 'qtb-engine.exe');
if (!fs.existsSync(exe)) {
  console.error(`[pack] 未找到产物：${exe}`);
  process.exit(1);
}
const mb = (fs.statSync(exe).size / 1024 / 1024).toFixed(1);
console.log(`\n[pack] 引擎打包完成：${exe}  (${mb} MB)`);
