# AI Drama Studio — Windows 安装与运行手册

> Repository: `zdingwl/ai-drama-studio`  
> Current product architecture: **Localized Remake V1**  
> Backend app version: **2.7.0**  
> Current final-video target: **local MiniMax H3**

这份文档只描述当前正式产品链。仓库中的旧 TransVLM / Shot / Character 历史脚本仍保留用于回归和兼容，但不要把它们当成当前整套产品的启动顺序。

当前真实产品链：

```text
原短剧
→ source understanding / Reference Clips
→ SourceDramaSnapshot
→ TargetCharacter / SceneLocalizationMapping
→ TargetDialogue / Qwen3-TTS
→ RemakeTimeline
→ GenerationSegment
→ MiniMax H3
→ H3 QC / Selected Output
→ LatentSync
→ safe background audio
→ subtitles / EpisodeOutput
```

最终本机验收需要多个隔离 Runtime。**不要把所有模型依赖安装进主 `.venv`。**

---

## 1. 推荐环境

### Windows

```text
Windows 10/11 64-bit
PowerShell 5.1+ 或 PowerShell 7
```

### NVIDIA GPU

当前完整本地生成链依赖 NVIDIA GPU。显存需求由实际 MiniMax H3、Qwen3-VL、Qwen3-TTS 和 LatentSync 配置决定；不要再用旧 TransVLM 的 8 GB 建议代表整套重制系统。

首先确认：

```powershell
nvidia-smi
```

### 内存 / 磁盘

真实短剧会同时产生原视频、Proxy、Reference Clips、模型缓存、H3 attempts、后期段和 EpisodeOutput。建议使用 SSD/NVMe，并预留足够的模型与媒体空间。

---

## 2. 安装基础工具

推荐使用 WinGet：

```powershell
winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
winget install --id astral-sh.uv -e --source winget
winget install --id Gyan.FFmpeg.Shared -e --source winget
```

同时安装 Microsoft Visual C++ 2015–2022 x64 Runtime。

安装后关闭旧 PowerShell，重新打开并检查：

```powershell
git --version
node --version
npm --version
uv --version
ffmpeg -version
ffprobe -version
nvidia-smi
```

前端仓库当前锁定：

```text
Node 22.18.0
```

见 `frontend/.node-version`。

---

## 3. 获取代码

```powershell
cd D:\
git clone https://github.com/zdingwl/ai-drama-studio.git
cd D:\ai-drama-studio
git status
git log -5 --oneline
```

更新：

```powershell
cd D:\ai-drama-studio
git pull --ff-only
```

如果本机存在未提交修改，不要直接覆盖；先检查 `git status`。

---

## 4. 主工程 Python 环境

当前 Windows 开发基线继续使用 Python 3.12：

```powershell
cd D:\ai-drama-studio
uv python install 3.12
uv venv .venv --python 3.12
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

激活：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

验证：

```powershell
python -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

主 `.venv` 负责业务 API、数据库、基础媒体、Breakdown/Character 等工程代码。H3、Qwen3-TTS、LatentSync、Audio Separator 等重模型 Runtime 应保持隔离。

### Character V10.1 GPU

当前 `engine/requirements.txt` 使用 `onnxruntime-gpu[cuda,cudnn]==1.21.1`。不能只看 `get_available_providers()`；需要实际创建模型 Session 才能证明 CUDA Provider 可用。

人物模型状态/准备入口：

```text
GET  /api/models/f05/status
POST /api/models/f05/prepare
```

---

## 5. 前端

```powershell
cd D:\ai-drama-studio\frontend
npm install
npm run dev
```

默认：

```text
http://127.0.0.1:5173
```

正式普通用户区域只有：

```text
Project
Review Center
Output
```

不要再按旧“01–06 全部暴露给用户”的文档判断当前 UI。

---

## 6. 启动 Studio Backend

新开 PowerShell：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8000
```

开发时可以加 `--reload`，真实长任务验收时不建议依赖自动 reload。

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

预期至少包含：

```json
{
  "status": "ok",
  "architecture": "localized-remake-h3-local-v1",
  "app_version": "2.7.0"
}
```

---

## 7. 当前隔离 Runtime 总表

| Runtime | 默认地址 | Backend 配置 | 用途 |
|---|---|---|---|
| Qwen3-VL OpenAI-compatible | `http://127.0.0.1:8001/v1` | `AI_DRAMA_VLM_BASE_URL`, `AI_DRAMA_VLM_MODEL`, `AI_DRAMA_VLM_API_KEY` | 内容语义 / H3 semantic QC |
| Qwen3-TTS | `http://127.0.0.1:7861` | `AI_DRAMA_TTS_BASE_URL` | 目标人物声音 / 目标对白 |
| LatentSync 1.6 | `http://127.0.0.1:7862` | `AI_DRAMA_LIPSYNC_BASE_URL` | 目标说话人口型 |
| Audio Separator | `http://127.0.0.1:7863` | `AI_DRAMA_BACKGROUND_AUDIO_BASE_URL`, `AI_DRAMA_BACKGROUND_AUDIO_MODEL` | 安全背景音 |
| MiniMax H3 FL2VA | `http://127.0.0.1:30010` | `AI_DRAMA_H3_FL2VA_URL` | H3 generation |
| MiniMax H3 Ref2VA | `http://127.0.0.1:30011` | `AI_DRAMA_H3_REF2VA_URL` | Reference Video H3 generation |

这些端口都默认绑定 localhost。除非你明确做好鉴权和网络隔离，不要把重模型 worker 直接暴露到公网。

---

## 8. Qwen3-VL

当前业务按 **OpenAI-compatible** 接口访问 Qwen3-VL。

Backend 至少需要：

```powershell
$env:AI_DRAMA_VLM_BASE_URL="http://127.0.0.1:8001/v1"
$env:AI_DRAMA_VLM_MODEL="Qwen3-VL-4B-Instruct"
$env:AI_DRAMA_VLM_API_KEY="EMPTY"
```

服务必须至少能响应：

```text
GET {AI_DRAMA_VLM_BASE_URL}/models
POST {AI_DRAMA_VLM_BASE_URL}/chat/completions
```

仓库当前**没有**为你的具体 Qwen3-VL serving stack 锁定一个通用的一键启动命令，因为不同本机可能使用不同 OpenAI-compatible server。不要把旧 `setup_breakdown_vlm_runtime.ps1` 或 TransVLM worker 误认为当前 QC VLM 的统一启动器。

统一 Runtime checker 会验证 `/models` 可达，但模型列表返回绝对路径与配置 alias 不完全相等时只做诊断，不会因此假报服务不可用。

---

## 9. Qwen3-TTS worker

正式 worker：

```text
scripts/qwen3_tts_worker_v1.py
```

它必须运行在自己的 Qwen3-TTS Python 环境，**不要**把 `qwen-tts` 重依赖强塞主 `.venv`。

Required environment：

```powershell
$env:AI_DRAMA_QWEN3_TTS_VOICE_DESIGN_MODEL_PATH="D:\models\..."
$env:AI_DRAMA_QWEN3_TTS_BASE_MODEL_PATH="D:\models\..."
```

Optional：

```powershell
$env:AI_DRAMA_QWEN3_TTS_DEVICE="cuda:0"
$env:AI_DRAMA_QWEN3_TTS_DTYPE="bfloat16"
$env:AI_DRAMA_QWEN3_TTS_ATTN="flash_attention_2"
$env:AI_DRAMA_QWEN3_TTS_HOST="127.0.0.1"
$env:AI_DRAMA_QWEN3_TTS_PORT="7861"
```

在已经准备好的独立 Qwen3-TTS 环境中：

```powershell
cd D:\ai-drama-studio
python .\scripts\qwen3_tts_worker_v1.py
```

Backend 默认访问 `http://127.0.0.1:7861`。状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/tts/runtime-status
```

仓库目前没有自动安装 Qwen3-TTS 模型/依赖的 setup 脚本；不要根据猜测安装版本。模型环境应按当前锁定的 Qwen3-TTS runtime 另行准备。

---

## 10. LatentSync 1.6 worker

正式 worker：

```text
scripts/latentsync_worker_v1.py
```

Required：

```powershell
$env:AI_DRAMA_LATENTSYNC_ROOT="D:\runtime\LatentSync"
```

Optional：

```powershell
$env:AI_DRAMA_LATENTSYNC_CONFIG="configs/unet/stage2_512.yaml"
$env:AI_DRAMA_LATENTSYNC_CHECKPOINT="checkpoints/latentsync_unet.pt"
$env:AI_DRAMA_LATENTSYNC_HOST="127.0.0.1"
$env:AI_DRAMA_LATENTSYNC_PORT="7862"
$env:AI_DRAMA_LATENTSYNC_DEEPCACHE="0"
```

在**官方 LatentSync 环境**中运行：

```powershell
cd D:\ai-drama-studio
python .\scripts\latentsync_worker_v1.py
```

Backend 状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/lip-sync/runtime
```

如果 `ready=false`，检查 worker 返回的 `root_ready / cuda_ready / error`，不要在主 `.venv` 里盲目重装 diffusers/torch。

---

## 11. Audio Separator R10.1

这一项仓库已经提供完整 Windows setup/start/check。

首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_audio_separator_runtime.ps1
```

启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_audio_separator_runtime.ps1
```

真实模型 inference 自检：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_audio_separator_runtime.ps1
```

默认模型：

```text
UVR-MDX-NET-Inst_HQ_5.onnx
```

业务上 Audio Separator 失效时会安全降级为 `TARGET_DIALOGUE_ONLY_FALLBACK`；它不会把原音轨低音量混回成片。但是**完整本机 R10.1 验收**仍要求 Audio Separator Runtime 真正 READY 并完成实际 separation 测试。

---

## 12. MiniMax H3

Backend 只连接隔离的本地 H3 SGLang 服务：

```text
FL2VA  http://127.0.0.1:30010
Ref2VA http://127.0.0.1:30011
```

可覆盖：

```powershell
$env:AI_DRAMA_H3_FL2VA_URL="http://127.0.0.1:30010"
$env:AI_DRAMA_H3_REF2VA_URL="http://127.0.0.1:30011"
$env:AI_DRAMA_H3_MODEL="MiniMaxAI/MiniMax-H3"
```

Backend 会依次探测 H3 service 的 `/health` 与 `/v1/models`。

状态：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/h3/runtime
```

**当前仓库没有锁定一个可对所有显卡/显存配置通用的 H3 SGLang Windows 启动脚本。** 请使用你已经准备并验证过的 MiniMax H3 FL2VA / Ref2VA serving 命令。这里不提供未经验证的推测参数。

真实生成约束由业务代码负责：

```text
H3 render 4..15s
>15s -> balanced multi-segment split
<4s  -> H3 render >=4s + exact FFmpeg post-trim
```

---

## 13. 一次检查整套 Runtime

Backend 启动后，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1
```

输出只关心：

```text
Backend
H3 FL2VA
H3 Ref2VA
Qwen3-VL
Qwen3-TTS
LatentSync
Audio Separator
```

全部必须是：

```text
READY
```

JSON：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_local_remake_runtime_stack.ps1 -Json
```

这个脚本**只读**：不下载模型、不启动服务、不修改项目。

---

## 14. 真实 Project 端到端验收

### 只检查项目当前状态

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID
```

### 按缺失阶段断点续跑

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_real_project_acceptance_v1.ps1 `
  -ProjectId PROJECT_你的项目ID `
  -Run
```

脚本会按当前事实跳过已完成阶段：

```text
已有 GenerationSegment -> 不重跑自动准备
已有全部 Selected Output -> 不重跑 H3
已有完整 PostProduction / EpisodeOutput -> 不重跑后期
```

如果出现 ReviewIssue：

```text
Result: NEEDS_REVIEW
```

去 Review Center 修改真实业务数据，再执行同一个 `-Run` 命令继续。

机器链全部完成后最多只返回：

```text
READY_FOR_MANUAL_ACCEPTANCE
```

**这不等于最终 PASS。** 必须人工看/听 MP4 + SRT。

详细清单见 `docs/REAL_PROJECT_ACCEPTANCE.md`。

---

## 15. 人工最终检查

至少检查：

1. 人物身份稳定，且没有原演员泄漏；
2. 场景 KEEP/LOCALIZE 与目标地区策略一致；
3. 动作、镜头、构图、运镜与参考意图一致；
4. 目标语言对白自然；
5. 目标对白真实说话时长和画面时长匹配；
6. 多人镜头口型打在正确目标说话人脸上；
7. 不存在可听见的原语言对白残留；
8. 背景音乐/环境音/SFX 与目标对白混音自然；
9. SRT 时间正确且跨 GenerationSegment 对白不重复；
10. 最终 Episode MP4 可播放、可导出、音画同步。

---

## 16. 常见故障

### Backend NOT READY

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

以及运行 Backend 的 PowerShell 日志。

### H3 FL2VA / Ref2VA NOT READY

检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/h3/runtime
```

确认对应 30010/30011 serving process 真正存在，不要只看模型文件是否下载。

### Qwen3-VL NOT READY

确认：

```powershell
$env:AI_DRAMA_VLM_BASE_URL
$env:AI_DRAMA_VLM_MODEL
```

以及：

```powershell
Invoke-RestMethod "$env:AI_DRAMA_VLM_BASE_URL/models"
```

### Qwen3-TTS NOT READY

检查独立 worker `/health` 与 Backend：

```powershell
Invoke-RestMethod http://127.0.0.1:7861/health
Invoke-RestMethod http://127.0.0.1:8000/api/tts/runtime-status
```

### LatentSync NOT READY

```powershell
Invoke-RestMethod http://127.0.0.1:7862/health
Invoke-RestMethod http://127.0.0.1:8000/api/lip-sync/runtime
```

重点看 `root_ready`、`cuda_ready` 和 `error`。

### Audio Separator NOT READY

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_audio_separator_runtime.ps1
```

这个检查会做一次真实 separation，不只是 `/health`。

### H3 / PostProduction 卡住

先检查：

```text
Project -> Review Center
```

真实不确定问题必须在对应领域编辑器解决。不要直接改数据库，也不要为了“跑通”把 H3_QC / LIP_SYNC_QC 标记 Ignore。

---

## 17. 旧 Source-analysis / TransVLM 资料

仓库保留：

```text
scripts/setup_transvlm_runtime.ps1
scripts/check_transvlm_runtime.ps1
旧 Breakdown / TransVLM 文档
```

它们属于历史/特定 source-analysis runtime，不代表当前 Localized Remake V1 的完整 H3/TTS/LipSync/Audio stack。

如果当前 `PROJECT_STATE.md` 明确某个 source-understanding profile 仍依赖这些工具，再按对应冻结文档使用；否则不要为了启动当前最终成片链重复安装旧 Runtime。

---

## 18. 当前验收边界

仓库代码和独立 CI 通过，不代表你的 GPU、模型权重和真实短剧已经通过。

当前事实仍然是：

```text
R7/R8/R9/R10/R10.1 CODE + ISOLATED REPOSITORY ACCEPTANCE = PASS
FRONTEND BUILD ACCEPTANCE = PASS
LOCAL H3 / QWEN / LATENTSYNC / AUDIO-SEPARATOR / REAL PROJECT ACCEPTANCE = PENDING
```

真实 Project 通过人工看/听之前，不要把本机 Release Gate 写成 PASS。
