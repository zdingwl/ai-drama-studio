# AI Drama Studio — Reference Video V2

本项目是 Windows 本地使用的 AI 短剧本地化重制工作台。

当前架构不再把“拉片”理解为生成一份尽可能详细的文字分析，而是把原视频拆成独立 Shot，并保存每个 Shot 的 **Reference Video**。后续人物、场景、关键道具、目标语言对白和声音作为控制条件参与重制。

## 当前实现

```text
F01 项目管理                    ✅
F02 多剧集导入 / 拖动排序         ✅
F03 视频预处理                  ✅ 代码完成，待本机真实视频验收
F04 自动拉片 / Reference Clip    ✅ 代码完成，待本机真实视频验收
F05 智能内容识别                ✅ V1 完成，待本机真实素材验收
F06-F13                       ⏳ 按 V2 架构继续开发
```

完整架构：`docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`

F05 详细 Contract：`docs/F05_CONTENT_ANALYSIS_V2.md`

## 核心流程

```text
项目
→ 多个 Episode
→ 顺序预处理
→ 顺序自动拉片
→ Shot + Reference Clip
→ 人物 / Scene / Key Prop / Dialogue
→ 人工审核
→ 替换资产 / Voice / 本地化
→ 按 Shot 规划重制策略
→ Reference Video 视频重制
→ 弹性时间轴
→ QC / Export
```

批量处理始终按 `Episode.sort_order` 一集一集执行，不并行跑多个剧集。

## 技术栈

Backend：
- Python
- FastAPI
- SQLAlchemy
- SQLite
- FFmpeg / FFprobe
- TransNetV2（F04 本地切镜）
- OpenCV YuNet + SFace + HOG（F05 人物视觉证据）
- faster-whisper（F05 源对白 ASR）

Frontend：
- Vue 3
- TypeScript
- Vue Router
- Vite

## 本地运行

### 1. Python 环境

Windows PowerShell 示例：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r engine\requirements.txt
```

确认：

```powershell
ffmpeg -version
ffprobe -version
```

### 2. 准备 F05 人物视觉模型

可以在 F05 页面点击“准备人物模型”，也可以命令行执行：

```powershell
python -m engine.app.content_models_v2
```

固定下载并校验：
- YuNet；
- SFace。

模型默认保存到：

```text
data_v2/models/f05/
```

### 3. F05 Whisper 配置

默认：

```text
AI_DRAMA_WHISPER_MODEL=small
AI_DRAMA_WHISPER_DEVICE=auto
```

可选覆盖：

```powershell
$env:AI_DRAMA_WHISPER_MODEL="small"
$env:AI_DRAMA_WHISPER_DEVICE="cuda"
$env:AI_DRAMA_WHISPER_COMPUTE_TYPE="float16"
```

如果 CUDA 运行初始化失败，F05 会尝试退回 CPU int8。

### 4. 可选 Speaker Diarization

Speaker 不是默认强制依赖。

如果你已经在本机准备好兼容的 pyannote Pipeline，并安装了对应 `pyannote.audio`，设置：

```powershell
$env:AI_DRAMA_DIARIZATION_MODEL_PATH="E:\models\pyannote-speaker-diarization-community-1"
```

未配置时 F05 会明确显示：

```text
Speaker = NOT_CONFIGURED
```

不会让人物/Scene/ASR 一起失败。

### 5. 启动后端

```powershell
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```text
GET http://127.0.0.1:8000/api/health
```

应返回 architecture=`reference-video-v2`。

### 6. 启动前端

```powershell
cd frontend
npm install
npm run dev
```

Vite 会把 `/api` 代理到 `127.0.0.1:8000`。

## V2 本地数据

默认：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
│  └ f05/
└ workspace/
```

可以设置：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

再启动后端，把数据库、模型和视频工作区放到指定目录。

## 当前用户操作

### F01 新建项目

填写：
- 项目名称；
- 原项目语言；
- 目标语言；
- 目标地区。

### F02 导入剧集

支持一次导入多个视频，并拖动排序。

### F03 视频预处理

支持单集处理或“顺序批量预处理”。

输出：
- proxy.mp4；
- audio.wav（原视频有音轨时）；
- Media Info。

### F04 自动拉片

支持单集拉片 / 重新拉片和顺序批量拉片。

每个 Shot 输出：
- start/end/duration；
- Reference Clip；
- Thumbnail。

Reference Clip 是后续视频重制的正式输入资产。

### F05 智能内容识别

按整个 Project 顺序分析全部 Episode，当前输出：

```text
Character Candidate
Character Track
Scene Candidate
Analysis Dialogue
Speaker Segment（可选）
Speaker → Character Candidate（证据足够时）
```

人物识别不是纯 Face：

```text
YuNet / SFace
+ HOG Person Detection
+ Body / Clothing Evidence
```

背影可以形成 body-only Track；但无脸身体证据只做保守相邻 Shot 合并。

关键道具目前已经有正式数据结构，但默认对象模型尚未配置，因此不会把普通环境物体伪造成“剧情关键道具”。

F05 页面会分别显示每个子组件的真实状态。

## 测试

V2 默认测试：

```powershell
pytest
```

当前 `pyproject.toml` 只把 `engine/tests/v2` 作为新架构默认 Gate。旧 `engine/tests/unit` 属于 Legacy 测试资料。

F03-F05 仍必须用真实短剧视频在目标 Windows 机器验收，因为需要确认：
- FFmpeg；
- TransNetV2；
- YuNet/SFace/HOG；
- Faster Whisper；
- 真实多剧集人物跨 Shot 聚类；
- Scene 聚类；
- Vue 浏览器交互。

## Legacy

仓库里可能仍存在旧业务代码和旧文档，以便必要时参考算法实现；它们不属于 V2 产品 Contract，也不会从 V2 FastAPI 入口或新 Router 加载。
