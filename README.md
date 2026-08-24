# AI Drama Studio — Reference Video V2

本项目是 Windows 本地使用的 AI 短剧本地化重制工作台。

当前架构不再把“拉片”理解为生成一份尽可能详细的文字分析，而是把原视频拆成独立 Shot，并保存每个 Shot 的 **Reference Video**。后续人物、场景、关键道具、目标语言对白和声音作为控制条件参与重制。

## 当前实现

```text
F01 项目管理                    ✅
F02 多剧集导入 / 拖动排序         ✅
F03 视频预处理                  ✅ 代码完成，待本机真实视频验收
F04 自动拉片 / Reference Clip    ✅ 代码完成，待本机真实视频验收
F05-F13                       ⏳ 按 V2 架构继续开发
```

完整架构：`docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`

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

### 2. 启动后端

```powershell
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```text
GET http://127.0.0.1:8000/api/health
```

应返回 architecture=`reference-video-v2`。

### 3. 启动前端

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
└ workspace/
```

可以设置：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

再启动后端，把数据库和视频工作区放到指定目录。

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

## 测试

V2 默认测试：

```powershell
pytest
```

当前 `pyproject.toml` 只把 `engine/tests/v2` 作为新架构默认 Gate。旧 `engine/tests/unit` 属于 Legacy 测试资料。

F03/F04 仍必须用真实短剧视频在目标 Windows 机器验收，因为需要确认本机 FFmpeg、TransNetV2 权重、CPU/GPU 环境和真实 Reference Clip 边界。

## Legacy

仓库里可能仍存在旧业务代码和旧文档，以便必要时参考算法实现；它们不属于 V2 产品 Contract，也不会从 V2 FastAPI 入口或新 Router 加载。
