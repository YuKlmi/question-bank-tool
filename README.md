# question-bank-tool

把 Word/PDF 题库结构化成本地可练习的题目：解析分段、答案回填、答题判分、批注与错题复习。Electron + Python，单机离线。

## Quick Start

### 环境要求

| 依赖 | 版本 | 说明 |
|---|---|---|
| Windows | — | 目前只支持 Windows |
| Python | 3.14.5（已验证） | 解析引擎；依赖均为预编译轮子，不需要编译器 |
| Node.js | 24.15.0（已验证） | 桌面壳（Electron）与界面（Vue 3） |
| Microsoft Office | 可选 | **只有**解析旧版 `.doc` 时需要 |

> `.doc` 是 OLE 二进制格式，转换走 Word COM，所以依赖本机装 Office；
> `.docx` 与文本型 `.pdf` 不需要 Office。

### 安装

```bash
git clone https://github.com/YuKlmi/question-bank-tool.git
cd question-bank-tool

python -m pip install -r engine/requirements.txt
npm install
```

### 运行

```bash
npm run dev
```

会先起 Vite 开发服务器，就绪后再拉起 Electron 窗口。

### 测试

```bash
npm run test:engine   # 解析引擎：规则切分 / 流水线回归 / 服务层 / RPC 契约（91 项）
npm test              # 桌面壳 ↔ 引擎：子进程启停 / JSON-RPC / 并发（6 项）
npm run test:e2e      # 真实 Electron 端到端冒烟（18 项）
```

`npm run test:engine` 依赖 `samples/` 里的回归样例；缺失会直接失败。

### 打包（可选）

```bash
npm run pack   # 免安装目录 → release/win-unpacked/
npm run dist   # portable + NSIS 安装包
```

打包会把 Python 引擎经 PyInstaller 打成单文件 exe 随应用分发，产物不依赖本机 Python。
若 `%LOCALAPPDATA%` 写入受限导致报 `Access is denied`，见 `AGENTS.md` 的「打包注意」。

## 文档

设计与实测结论都在 [AGENTS.md](./AGENTS.md)：三份样例的版面勘察、四段式解析流水线、
答案对照算法（三次迭代）、数据模型、里程碑与已知限制。

> 动手改解析规则前建议先读它——题库格式的坑基本都记在里面了。
