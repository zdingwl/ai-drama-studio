# P14 Windows 原生 IndexTTS-2.5：无需 WSL 的统一运行时

> 日期：2026-09-12  
> 状态：P14 本地部署整改；本文优先级高于 `docs/35`、`docs/36`、`docs/37` 中“Windows 必须使用 WSL2/vLLM-Omni”的运行方式。  
> 本文只改变 Provider runtime 的部署实现，不改变 P14 Artifact、人工听审与能力状态：`TTS = PLANNED / TIMING = PLANNED / P14 PASS = NO`。

## 1. 决策

Windows 正式本地开发/验收路径不再要求 WSL2。

统一入口仍然只有：

```text
start.cmd
```

Windows 的 P14 TTS runtime 改为：

```text
AI Drama Studio launcher (Python 3.12+)
├─ FastAPI backend (Python 3.12+)
├─ Vite frontend
└─ IndexTTS-2.5 native Windows sidecar
   ├─ official IndexTTS source
   ├─ isolated uv environment (Python 3.10/3.11)
   ├─ CUDA PyTorch on Windows
   ├─ IndexTTS2.infer_v2_5
   └─ local compatibility adapter :8092
```

Linux 继续保留 vLLM-Omni 路径。P14 仍只有一个 TTS 模型：`IndexTeam/IndexTTS-2.5`；“Windows native / Linux vLLM-Omni”只是同一模型的不同本地 serving runtime，不是多 Provider 产品选择。

## 2. 为什么需要独立 Python 环境

AI Drama Studio backend 要求 Python 3.12+；IndexTTS 官方当前 `pyproject.toml` 明确要求：

```text
requires-python = >=3.10,<3.12
```

因此二者不能可靠共用一个 virtualenv。

Windows 启动器在：

```text
.runtime/indextts25-native-windows/source/.venv
```

维护官方 IndexTTS 的独立 `uv` 环境。`uv sync` 会按上游 lock/pyproject 选择合适 Python，不要求用户把 Studio backend 降级到 3.11。

## 3. 上游来源与版本

Windows runtime 只读取官方仓库：

```text
https://github.com/index-tts/index-tts
```

当前工程固定源代码 commit：

```text
ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c
```

这样首次真实验收期间不会因为上游 main 漂移而改变生成行为。

模型仍从 ModelScope 下载：

```text
IndexTeam/IndexTTS-2.5
-> .models/IndexTTS-2.5
```

## 4. Windows 原生 Adapter

`scripts/indextts25_native_server.py` 不伪造语音模型。它直接：

```text
from indextts.infer_v2_5 import IndexTTS2
```

加载官方 IndexTTS-2.5，然后调用：

```text
IndexTTS2.infer(
  spk_audio_prompt=reference_audio,
  text=final_target_dialogue,
  lang=...,
  use_emo_text=True,
  emo_alpha=...,
  duration_factor=...,
)
```

Adapter 只保持 AI Drama Studio 已经稳定的本地 wire contract：

```text
GET  /health
GET  /v1/models
POST /v1/audio/speech
```

因此 P14 现有 ProviderJob-before-call、真实 WAV 落盘、ffprobe、NEEDS_REVIEW、ACCEPT、Artifact Graph 与 Timing 逻辑都不需要因为 Windows runtime 改写。

## 5. GPU 边界

不装 WSL 可以，但 Windows 原生高质量 IndexTTS 仍需要本机 NVIDIA/CUDA 能被 PyTorch 识别。

原生 adapter 启动时会检查：

```text
torch.cuda.is_available()
```

CUDA 不可见时 fail closed，并明确报错；不会偷偷回退到 CPU 后让用户等待极长时间并误以为系统卡死。

WSL2 不再是系统前置条件。仍需：

```text
Python 3.12+       # Studio backend launcher
Node.js 22+
Git
NVIDIA 驱动 / CUDA-compatible GPU runtime
```

IndexTTS 自己需要的 Python 3.10/3.11 由 `uv` 的隔离环境管理。

## 6. 首次启动

用户只运行：

```text
git pull
start.cmd
```

启动器自动：

1. 准备 Studio `.venv`；
2. 安装/获得 `uv`；
3. clone 官方 IndexTTS 到 `.runtime/indextts25-native-windows/source`；
4. checkout 固定 upstream commit；
5. `uv sync` 官方依赖；
6. 为本地 adapter 加入 FastAPI/Uvicorn；
7. 缺模型时通过 ModelScope 下载到 `.models/IndexTTS-2.5`；
8. 原生加载 CUDA IndexTTS-2.5；
9. 8092 就绪后沿用 `/v1/models` readiness；
10. 同时运行 Studio backend/frontend。

第一次仍可能较慢，因为需要下载 Python runtime、PyTorch/IndexTTS 依赖和大模型。之后全部复用本地缓存。

## 7. 情绪与语速

Windows native adapter 继续执行 IndexTTS-2.5 原生能力：

```text
use_emo_text = true
emo_alpha = 0.6 (当前默认)
duration_factor = 1.0 (当前首次候选默认)
```

Reference Voice 仍来自显式绑定的 reference audio；不得从原剧演员音轨静默克隆。

当前 wire schema 里的 `speed` 是 P14 未 PASS 前保留的兼容字段。Windows adapter 在当前默认值 `1.0` 下把它交给官方 `duration_factor`。未来若开放人工 retake 的非 1.0 时长调整，应在正式 typed contract 中清理该字段命名，避免“speed factor”和“duration factor”方向语义混淆。

## 8. 验收状态

Windows 原生服务 READY 只代表 Provider runtime 能用，不代表 P14 PASS。

仍然必须完成：

```text
真实 Reference Voice
-> 真实 IndexTTS WAV
-> ffprobe actual_speech_duration_us
-> 逐句人工听审
-> ACCEPT TARGET_AUDIO
-> TIMING_PLAN
-> overflow 处理
-> 用户明确 P14 PASS
```

在此之前：

```text
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```
