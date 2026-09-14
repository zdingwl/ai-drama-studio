# P16 Video Generation / QC / Selection 数据契约

> 日期：2026-09-13  
> 状态：正式工程合同。P16 使用统一 H3 Generation Runtime boundary：Windows 默认 `LOCAL_COMFYUI` 本地 MiniMax-H3，`LOCAL_SGLANG` 保留为 Linux / 私有 GPU 显式本地模式，MiniMax Cloud V2 仅作为显式可选 fallback；不得在本地失败后自动切换付费云端。  
> 最终真实 Runtime 与人工验收前 `VIDEO_GENERATION / QC_SELECTION = PLANNED`。

## 1. 唯一职责

P16 只负责：

```text
CURRENT GENERATION_SEGMENTS
+ CURRENT TARGET_STORYBOARD
+ CURRENT TARGET_ASSETS
        ↓
GenerationAttempt(s)
        ↓
Technical QC
        ↓
Human Semantic QC / Selection candidate
        ↓ explicit ACCEPT
GENERATED_VIDEO + GENERATION_SELECTION
```

GenerationAttempt 永远不是正式成片；只有 `GENERATION_SELECTION` 可进入 Post。

## 2. 正式硬输入

必须同时 CURRENT：

```text
TARGET_STORYBOARD
GENERATION_SEGMENTS
TARGET_ASSETS
```

并验证 Generation Segments 属于当前 Storyboard，Storyboard 属于当前 Assets lineage。

## 3. H3 Generation Runtime Boundary

P16 业务层只依赖统一 H3 Runtime 协议，不把 Artifact/Selection 合同绑定到某个付费 endpoint。

### 3.1 默认：Windows 原生 ComfyUI

```text
AI_DRAMA_P16_H3_RUNTIME=LOCAL_COMFYUI   # default
AI_DRAMA_P16_H3_COMFYUI_BASE_URL=http://127.0.0.1:8188
UNET=minimax_h3_fl2va_pruned_int8_convrot.safetensors
CLIP=qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
VIDEO_VAE=minimax_h3_video_vae_fp16.safetensors
AUDIO_VAE=minimax_h3_audio_vae_fp32.safetensors
```

所有 P16 Runtime 配置必须通过后端 canonical `Settings` 读取，因此 `backend/.env` 与进程环境变量具有同一语义；不得一部分字段走 Pydantic Settings、另一部分直接 `os.getenv()` 导致运行时读取不同配置源。

创建 P16 Task 前必须完成只读 readiness：

```text
GET ComfyUI /system_stats   -> 必须是兼容 ComfyUI JSON
GET ComfyUI /object_info    -> 必须存在 H3 原生节点及配置的四类模型文件
GET Studio /projects/{project_id}/video-generation/runtime-readiness
```

readiness 至少区分 `READY / UNAVAILABLE / WARMING_UP / INCOMPATIBLE / MODEL_MISMATCH / NOT_CONFIGURED`。只有 `READY` 才允许创建本地 P16 generation Task；Runtime 未部署或模型仍在加载时不得先创建 Task/ProviderJob 再用失败结果充当 readiness 探测。

ComfyUI adapter 使用原生 H3 节点构建 API-format workflow：

```text
UNETLoader(FL2VA)
+ CLIPLoader(type=minimax)
+ Video VAE / Audio VAE
→ MiniMaxH3ImageToVideo
→ res_multistep + simple scheduler
→ joint video/audio sampling
→ VAEDecode + VAEDecodeAudio
→ CreateVideo(24fps)
→ SaveVideo(mp4)
```

Studio 通过 `POST /prompt → GET /history/{prompt_id} → GET /view` 驱动 workflow。第一版本地 ComfyUI adapter 使用官方 non-Turbo baseline：`short_edge=768`、`20 steps`、`res_multistep`、`simple` scheduler；视频按 24fps 生成，frame length 必须对齐 H3 `17k+5` 网格。输出为带原生音画的 MP4；在 `NATIVE_AUDIO_VIDEO` 模式下该正式音轨必须保留给 P17。

当前 P13 正式资产尚没有真实 `reference_media`，因此 P16 local v1 先使用 FL2VA partition 上的 `t2va`。Ref2VA 必须等真实 image/video/audio reference 可被 Runtime 访问后再接入；禁止把 Target Asset id、文字描述或不存在的 URI 伪装成 condition。

本地 ComfyUI loopback 请求必须 `trust_env=false`，禁止被系统 HTTP(S) proxy 代理；否则本机 Runtime 未启动时可能被代理错误伪装成 HTTP 502。

### 3.2 显式本地替代：SGLang

Linux / 私有 GPU 主机可以显式设置：

```text
AI_DRAMA_P16_H3_RUNTIME=LOCAL_SGLANG
AI_DRAMA_P16_H3_LOCAL_BASE_URL=http://127.0.0.1:30010
```

该模式继续执行 `GET /health + GET /v1/models` readiness，并通过 `POST /v1/videos → GET /v1/videos/{video_id} → GET /content` 生成。SGLang 同样属于本地 Runtime，不得因为失败自动切 Cloud。

### 3.3 显式 fallback：MiniMax Cloud

只有：

```text
AI_DRAMA_P16_H3_RUNTIME=MINIMAX_CLOUD
```

才读取 canonical server setting `AI_DRAMA_P16_MINIMAX_API_KEY` 并使用 `POST /v2/video_generation` + query V2 contract。API Key 仍只允许来自服务端 Secret settings，不进入 DB/Artifact/日志/Git。**本地 Runtime 不可用时禁止自动切云端**，避免意外产生费用。

### 3.4 共同规则

1. 无论本地或云端，每个 GenerationAttempt invocation 前必须先持久化 ProviderJob；
2. ProviderJob payload 只保存 prompt/hash/segment id/runtime profile 等安全信息；
3. Runtime job id / media URL 只作为 provenance；
4. Runtime 输出必须最终持久化到 Studio artifact storage；云端 URL 必须在失效前下载，本地 Runtime content 同样复制到受管 storage；
5. 保存 SHA256 并重新 ffprobe；
6. Runtime 未启动/未配置、warmup 未完成、服务接口不兼容、模型不匹配、生成失败、媒体不可读取、decode 失败均 fail closed；非 JSON create/query 错误必须安全保留 HTTP status、Content-Type 与截断后的响应摘要用于诊断；
7. retry 有上限；云端模式不得无限付费重试；
8. P15 必须把 Source Episode 比例映射到 H3 支持的 `21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16`；
9. H3 输出 duration 正式范围为整数 `4~15s`。planned GenerationSegment 可短于 4 秒，但 Runtime 请求至少 4 秒；P17 再按 authoritative segment timing trim/pad，不得反向改 Source timing。
10. 显式 retry 时若正式 Artifact lineage 或 Runtime/profile 任一发生变化，禁止复活旧 fingerprint Task；在原 Task 仍未超过 retry 上限、且当前 P16 正式输入仍完整 CURRENT 的前提下，基于当前 `TARGET_STORYBOARD + GENERATION_SEGMENTS + TARGET_ASSETS` 与当前 Runtime 创建 replacement P16 Task，并在 checkpoint 保留 `p16_replaces_failed_task_id`。当前正式输入缺失或 STALE 时仍必须 fail closed。

## 4. GenerationAttempt

每次 attempt 至少记录：

```text
attempt_id
project_id
generation_segments_artifact_id
generation_segment_id
attempt_number
provider_job_id
provider / model
prompt_fingerprint
remote_job_id?
media_url (local API URL)
media_sha256
mime_type
actual_duration_us
width / height / codec
technical_qc_status
technical_qc_issues[]
correction_from_previous_attempt[]
created_at
```

Attempt 为生产记录，不是 Artifact current pointer。

## 5. Technical QC

每个下载视频必须重新执行：

- 文件存在且 SHA256 一致；
- ffprobe 可 decode；
- duration > 0；
- duration 与本次 **H3 requested duration**（`clamp(ceil(planned_seconds), 4, 15)`）在配置容差内；planned segment 若短于 4 秒由 P17 确定性 trim，不作为 P16 QC 失败；
- width / height > 0；
- video stream 存在；
- codec 可由 ffmpeg 读取。

技术 QC FAIL 时可在有限 attempt 内重试；correction 必须明确上一轮技术失败原因。

## 6. Semantic QC 与 Selection

P16 v1 不允许技术脚本自动声称“人物/动作/场景语义通过”。当每个 GenerationSegment 至少有一个 Technical QC PASS attempt 后，形成 `NEEDS_REVIEW` Selection candidate：

```text
segment_id -> selected_attempt_id
```

普通用户逐段预览视频，并人工检查：

- Target Character / Scene / Prop 与目标设定一致；
- 无明显 Source actor identity 泄漏；
- 动作完成；
- 构图/运镜符合 Target Storyboard；
- 连续性可接受；
- 无明显生成崩坏。

用户显式 ACCEPT 即同时完成 v1 的 human semantic QC 与 selection 决策。

## 7. Publication

ACCEPT 后同一事务发布：

```text
GENERATED_VIDEO
GENERATION_SELECTION
```

`GENERATED_VIDEO` 是当前 selection 所选本地媒体集合的 typed Artifact；`GENERATION_SELECTION` 记录每个 segment 的 selected attempt 和 review 结论。

Graph 至少：

- `GENERATION_SEGMENTS -> GENERATED_VIDEO : DERIVED_FROM`
- `TARGET_STORYBOARD -> GENERATED_VIDEO : USES`
- `TARGET_ASSETS -> GENERATED_VIDEO : USES`
- `GENERATED_VIDEO -> GENERATION_SELECTION : DERIVED_FROM`
- `TARGET_STORYBOARD -> GENERATION_SELECTION : USES`

只有 CURRENT `GENERATION_SELECTION` 可被 P17 消费。

## 8. Professional Skill

新增：

```text
video-generation-qc@1.1.0
required capabilities = VIDEO_GENERATION + QC_SELECTION
```

Provider execution 与 Artifact publication 必须分离；Provider 不能生成正式 Artifact ids/revision/fingerprint。

## 9. UI

普通用户“视频生成”工作区至少提供：

- 显式启动生成；
- 运行状态；
- Runtime readiness；未就绪时禁用生成 Command，并给出可操作原因；
- 每个 GenerationSegment 的 attempt 视频与技术 QC；
- 只允许选择 Technical QC PASS attempt；
- 显式确认 Selection 或拒绝重新生成；
- GET 无副作用。

## 10. 完成定义

工程完成至少包括 local-first H3 Runtime adapter、显式 Cloud fallback、ProviderJob-before-invocation、媒体受管持久化、ffprobe QC、Attempt storage、Selection candidate/review/publication、Artifact Graph、UI、tests。真实本地 H3 Runtime、真实生成音画与真人质量验收仍必须在统一验收时完成，不能由 mock 单测代替。
