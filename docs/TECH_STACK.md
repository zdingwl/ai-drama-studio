# AI Drama Studio — Technical Stack & Runtime Rules

## 1. 产品运行方式

本项目当前定位：

- 本地自用
- 单用户
- Windows 为主要开发和使用环境
- 当前 GPU：NVIDIA RTX 4060 Ti 16GB
- 开发阶段不追求高吞吐，不以速度作为阻塞条件
- 先验证完整生产流程，再优化性能

因此第一版禁止为了“以后可能需要”提前引入 SaaS 重架构。

---

## 2. 固定技术栈

### UI / Desktop

```text
Vue 3
TypeScript
Vite
Pinia
Electron（后置）
```

开发阶段优先直接运行：

```text
Vue Dev Server: http://localhost:5173
FastAPI:        http://localhost:8000
```

核心流程稳定后再将 Vue + Python Engine 封装进 Electron。

### AI / Backend

```text
Python 3.11
FastAPI
PyTorch
CUDA
OpenCV
FFmpeg
FFprobe
```

Python 是 AI Engine，不要求业务层全部重写成 Python。

### 数据

```text
SQLite
SQLAlchemy
Alembic
Local Filesystem
```

第一版不引入：

- PostgreSQL（除非后续确有需要）
- Kubernetes
- Redis Cluster
- MinIO Cluster
- 多租户
- 复杂 RBAC
- 在线 Billing
- GPU Cluster

---

## 3. 应用架构

```text
┌────────────────────────────────────────┐
│ Vue 3 / Electron                       │
│ Project / Timeline / Player / Review   │
└───────────────────┬────────────────────┘
                    │ HTTP / WebSocket
                    ▼
┌────────────────────────────────────────┐
│ FastAPI Local Engine                   │
│                                        │
│ Project Service                        │
│ Media Service                          │
│ Shot Service                           │
│ Character Service                      │
│ Dialogue Service                       │
│ Scene Service                          │
│ Bible Service                          │
│ Generation Service                     │
│ QC Service                             │
│ Voice / LipSync / Render Service       │
└──────────────┬───────────────┬─────────┘
               │               │
               ▼               ▼
        Local AI / CUDA     Provider API
               │               │
               ▼               ▼
          Local Workspace    VLM / Video
          + SQLite           TTS / LipSync
```

---

## 4. 本地模型与 API 的分工

原则：

> 高频、确定性、适合本地 GPU、调用量大的能力尽量本地；决定最终内容质量、更新非常快的生成能力优先 API。

### 本地优先

- FFmpeg / FFprobe
- OpenCV
- Shot Detection
- Scene Embedding
- Face Detection / Tracking / Embedding
- Whisper / WhisperX
- Speaker Diarization
- Character / Scene similarity
- Technical QC
- Basic consistency QC
- Final Render

### API 优先

- 强 VLM
- Character Bible 语义分析
- Scene Bible 语义分析
- Shot Understanding
- Prompt 辅助编译
- Video Generation
- 高质量 TTS
- 高质量 Lip Sync
- 高阶 Semantic QC

### 开发阶段不要自研

- 视频基础生成模型
- 大型 VLM
- ASR 基础模型
- TTS 基础模型

项目核心资产是 Production Workflow / Contract / QC / Human Review，不是训练基础模型。

---

## 5. RTX 4060 Ti 16GB 规则

开发阶段必须假设 16GB 显存长期存在。

默认策略：

```text
GPU concurrency = 1
```

任务模式：

```text
需要 Whisper
→ load
→ run
→ unload
→ empty cache

需要 DINO
→ load
→ run
→ unload

需要 Face Embedding
→ load
→ run
→ unload
```

禁止为了省几秒把多个大型模型长期常驻显存。

性能慢可以接受，只要功能正确、结果可验证。

---

## 6. 推荐本地能力

### 视频处理

```text
FFmpeg
FFprobe
OpenCV
```

用于：转码、Proxy、抽音频、抽帧、切片、合成、技术 QC。

### Shot Detection

开发期主路线：

```text
TransNetV2
```

可保留：

```text
PySceneDetect
```

作为兜底或对比。

### Scene Embedding

推荐：

```text
DINOv2
```

负责关键帧视觉特征，不负责 Scene 的自然语言命名。

### ASR

推荐：

```text
Whisper
WhisperX
```

第一阶段重点获得文本和时间码。

### Speaker

推荐 Speaker Diarization + 时间重叠，再逐步加入 Active Speaker。

### Face / Character

实现必须通过抽象接口：

```text
FaceDetector
FaceTracker
FaceEmbedder
CharacterClusterer
```

不要把业务代码绑死到某一模型或 SDK。

---

## 7. Provider Adapter

所有闭源 API 必须经过 Provider Adapter。

禁止：

```python
run_minimax(...)
run_seedance(...)
run_runway(...)
```

业务层应使用：

```python
video_generation.generate(request)
```

统一请求示意：

```json
{
  "shot_id": "SHOT_023",
  "task_type": "reference_to_video",
  "prompt": "...",
  "duration": 5,
  "aspect_ratio": "9:16",
  "resolution": "1080p",
  "reference_images": [],
  "reference_video": null,
  "audio": null,
  "provider": "auto",
  "model": null
}
```

统一响应示意：

```json
{
  "generation_id": "GENERATION_000123",
  "provider": "...",
  "model": "...",
  "provider_task_id": "...",
  "status": "completed",
  "output_path": "generations/SHOT_023/v003.mp4",
  "cost": 1.25,
  "metadata": {}
}
```

同样原则适用于：

- VLM
- LLM
- TTS
- Lip Sync

---

## 8. Prompt Compiler

Shot Specification 是模型无关数据。

Prompt Compiler 根据 Provider / Model 生成模型专属输入：

```text
Shot Specification
      ↓
Prompt Compiler
      ├ Provider A Prompt
      ├ Provider B Prompt
      └ Provider C Prompt
```

禁止把某一模型的 Prompt 结构写回 Shot Specification。

---

## 9. 本地文件结构

推荐：

```text
workspace/
└── project_001/
    ├── source/
    ├── proxy/
    ├── audio/
    ├── frames/
    ├── shots/
    ├── characters/
    ├── actors/
    ├── scenes/
    ├── generations/
    ├── voice/
    ├── lipsync/
    ├── cache/
    └── exports/
```

媒体文件不放 SQLite，数据库只存相对路径。

---

## 10. 前后端通信

普通 CRUD / 查询：HTTP JSON。

长任务进度：WebSocket。

统一任务状态：

```text
pending
running
completed
failed
cancelled
```

前端必须能看到：

- 当前任务
- 当前步骤
- 进度
- 错误原因
- 是否可重试

---

## 11. GPU 任务原则

任何 GPU Feature 都应支持：

- 单任务执行
- 取消
- 重试
- 模型释放
- 异常后恢复
- 只重跑当前 Feature / Shot

不得因为某一个 Shot 失败而要求重新分析整集。

---

## 12. Electron 规则

第一阶段不优先打包 Electron。

当核心工作流稳定后：

```text
Electron 启动
→ 检查 Python Engine
→ 启动 FastAPI 子进程
→ 打开 Vue UI
→ 退出时关闭 Engine / 释放 GPU
```

不要让 Electron / Node 承担 PyTorch AI 推理。

---

## 13. 技术选择优先级

出现多种方案时按以下顺序决策：

1. 能否稳定完成当前 Feature。
2. 是否容易测试和人工修正。
3. 是否能保持 Contract 稳定。
4. 是否可替换模型。
5. 是否适合 RTX 4060 Ti 16GB。
6. 最后才考虑性能优化。
