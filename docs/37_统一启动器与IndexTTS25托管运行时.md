# P14 统一启动器与 IndexTTS-2.5 托管运行时

> 日期：2026-09-12  
> 状态：P14 本地开发/验收运行方式整改；优先级高于 `docs/35`、`docs/36` 中要求用户分别下载模型、启动 8092、后端、前端的手工步骤。  
> 本文只改变运行与部署体验，不改变阶段验收状态：`TTS = PLANNED / TIMING = PLANNED / P14 PASS = NO`。

## 1. 产品决策

本地 AI Drama Studio 不再要求用户理解或手工维护以下独立步骤：

```text
ModelScope 下载
vLLM-Omni Python 环境
8092 IndexTTS 服务
Alembic migration
FastAPI backend
Vite frontend
```

统一改为一个仓库入口：

```text
Windows: start.cmd
Linux / WSL: ./start.sh
```

统一启动器负责检查、准备、启动和回收这些进程。

## 2. 为什么不是把 GPU 模型 import 进 FastAPI

“一体化”定义为单入口和统一生命周期，不定义为单 OS 进程。

IndexTTS-2.5 / vLLM-Omni 必须保持独立 GPU sidecar，因为 FastAPI 开发模式会 reload，生产模式也可能多 worker；如果模型直接 import 到 Web 进程，会出现重复加载模型、重复占用显存、reload 后残留 GPU worker 等问题。

因此正式本地结构为：

```text
AI Drama Studio launcher
├─ IndexTTS-2.5 managed sidecar (8092, Linux/WSL2)
├─ FastAPI backend (8000)
└─ Vite frontend (5173)
```

对用户仍然只有一次启动操作。

## 3. 首次启动自动准备

统一启动器会自动：

1. 创建/更新仓库根目录 `.venv` 并安装 `backend[dev]`；
2. `alembic upgrade head`；
3. 检查 Node.js 22+，必要时执行 `npm install`；
4. 启动 IndexTTS sidecar；
5. sidecar 在 `.runtime/indextts25/` 建立独立 Python 3.12 环境；
6. 固定安装 `vllm==0.28.0` + `vllm-omni[indextts2]==0.28.0`；
7. 缺模型时自动从 ModelScope 下载 `IndexTeam/IndexTTS-2.5` 到 `.models/IndexTTS-2.5`；
8. 用 vLLM-Omni 自带 `indextts2_5.yaml` 启动两阶段 TTS；
9. 启动 FastAPI 与 Vite；
10. Web 应用可用后自动打开浏览器。

`.runtime/`、`.models/`、`.venv/`、`frontend/node_modules/` 都是本地缓存，不进入 Git。

## 4. 中国环境

模型权重默认从 ModelScope 下载，不在启动时依赖 Hugging Face 主站。

IndexTTS 运行中若需要延迟获取辅助资源，默认：

```text
HF_ENDPOINT=https://hf-mirror.com
```

可以由用户显式环境变量覆盖。

Python 包源默认沿用环境；如果需要国内 PyPI mirror，可设置：

```text
AI_DRAMA_PYPI_INDEX=https://mirrors.aliyun.com/pypi/simple
```

## 5. Windows 边界

vLLM-Omni 官方不原生支持 Windows，因此 Windows 启动器自动把 **TTS sidecar** 放到 WSL2，FastAPI / Vite 继续在 Windows 本机运行。

系统级前置条件只有：

```text
Windows + WSL2 已启用
GPU 驱动 / WSL GPU passthrough 可用
Python 3.12+（Windows backend）
Node.js 22+
```

统一启动器不会静默安装或升级 GPU 驱动、Windows/WSL 内核，也不会触发系统重启。

## 6. IndexTTS 稳定版本锁

托管 runtime 固定：

```text
vllm 0.28.0
vllm-omni[indextts2] 0.28.0
```

该稳定版本已经包含正式 `vllm_omni/deploy/indextts2_5.yaml`。本地 model path 启动必须显式传这个 deploy config；不能只把本地目录交给自动识别后假定两阶段 pipeline 一定正确。

这同时修复了旧脚本的一个部署风险：旧脚本使用本地 model path 时未显式传 `indextts2_5.yaml`，可能得到 API server 已响应但模型 stage 未正确建立的 502。

## 7. 生命周期

启动器检测到已有健康 backend/frontend/IndexTTS 时会复用，不重复启动。

如果 8092 有一个不 READY 的旧 IndexTTS 进程，启动器会尝试清理匹配 `IndexTTS-2.5 + port 8092` 的旧 vLLM 进程一次；若端口仍被未知进程占用则 fail closed，不杀未知服务。

Ctrl+C 退出统一启动器时，只回收由本次启动器创建的进程；启动前已经存在并被复用的服务不由它关闭。

## 8. 用户操作

以后本地开发/验收推荐操作只有：

```text
git pull
start.cmd
```

Windows 也可以直接双击 `start.cmd`。

Linux / WSL：

```bash
git pull
./start.sh
```

首次启动时间较长是因为运行时与模型会自动下载；后续启动直接复用 `.runtime/` 和 `.models/`。

## 9. 验收状态不变

统一启动器成功、页面显示 `IndexTTS-2.5 READY` 只代表本地 Provider runtime ready，不代表 P14 真实人工验收完成。

仍需真实 Reference Voice、真实生成 WAV、ffprobe、逐句听审、正式 TARGET_AUDIO、TIMING_PLAN 与 overflow 处理，并由用户明确 `P14 PASS` 后才允许升级能力状态。
