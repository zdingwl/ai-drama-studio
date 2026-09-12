# P14 IndexTTS-2.5 本地运行时启动与健康检查

> 日期：2026-09-12  
> 状态：P14 工程运行手册补充；优先级高于旧的 OpenAI / 通用 TTS 启动说明。  
> 本文只建立本地运行与 readiness，不代表 P14 人工验收通过。`TTS / TIMING` 继续保持 `PLANNED`。

## 1. 唯一运行时

P14 只允许：

```text
IndexTeam/IndexTTS-2.5
vLLM-Omni
http://127.0.0.1:8092/v1
```

不再启动 OpenAI TTS、`tts-1`、`gpt-4o-mini-tts` 或其他 TTS Provider。

## 2. 前置环境

先按 IndexTTS-2.5 / vLLM-Omni 上游说明完成 GPU、CUDA、Python 与 vLLM-Omni 安装。仓库启动脚本不会静默安装 CUDA、驱动或模型运行时，也不会修改系统 Python。

IndexTTS-2.5 官方仓库：

```text
https://github.com/index-tts/index-tts
```

官方生产 serving 方式：

```bash
vllm serve IndexTeam/IndexTTS-2.5 \
  --omni \
  --trust-remote-code \
  --port 8092
```

## 3. 仓库启动入口

Linux / WSL：

```bash
./scripts/start_indextts25.sh
```

Windows PowerShell：

```powershell
./scripts/start_indextts25.ps1
```

PowerShell 脚本优先使用当前环境的 `vllm`；如果没有，则尝试 WSL2 内的 `vllm`。两者都不存在时 fail closed，不会自动下载安装。

## 4. CLI readiness

```bash
python scripts/check_indextts25.py
```

只有 `/v1/models` 实际返回并包含：

```text
IndexTeam/IndexTTS-2.5
```

才输出 `READY`。

## 5. 产品 readiness

`GET /api/v3/projects/{project_id}/target-audio/voices` 现在同时返回：

```text
configured
runtime_ready
runtime_message
voices
```

其中：

- `configured=true` 只表示 Reference Voice Catalog 非空；
- `runtime_ready=true` 才表示本地 IndexTTS 服务可访问，且目标模型真实加载；
- 前端生成按钮必须同时满足 `configured + runtime_ready + 所有对白完成显式声线绑定`；
- 服务离线或模型不匹配时不得创建真实生成候选。

## 6. 真实验收顺序

```text
启动 IndexTTS-2.5
-> 页面显示 READY
-> 选择有授权的 Reference Voice
-> 生成真实 WAV
-> 服务端 ffprobe
-> 人工逐句听审
-> ACCEPT TARGET_AUDIO
-> 计算 TIMING_PLAN
-> 处理所有 OVERFLOW
-> 人工确认
```

完成上述真实链路并由用户明确确认 `P14 PASS` 前：

```text
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```
