# AI Drama Studio — Reference Video V2

本项目是 Windows 本地使用的 AI 短剧本地化重制工作台。

> **Windows 首次安装 / TransVLM Runtime / 前后端启动 / 更新 / 故障排查请优先阅读：**
> `docs/INSTALL_AND_RUN_WINDOWS.md`
>
> 当前 02 拉片正式基线已经升级为 **Shot V5 TransVLM-first**。README 中较早的 F04/F05 技术描述仅保留项目演进背景；安装运行以以上手册和当前代码为准。

当前架构不再把“拉片”理解为生成一份尽可能详细的文字分析，而是把原视频拆成独立 Shot，并保存每个 Shot 的 **Reference Video**。后续人物、场景、关键道具、目标语言对白和声音作为控制条件参与重制。

## 当前实现

```text
F01 项目管理                    ✅
F02 多剧集导入 / 拖动排序         ✅
F03 视频预处理                  ✅ 代码完成，待本机真实视频验收
F04 自动拉片 / Reference Clip    ✅ 当前正式基线：Shot V5 TransVLM-first
F05 智能内容识别                ⚠️ 当前人物策略待重新规划
F06-F13                       ⏳ 按 V2 架构继续开发
```

完整架构：`docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md`

当前 Windows 安装运行手册：`docs/INSTALL_AND_RUN_WINDOWS.md`

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

## 当前拉片技术栈

Backend：
- Python / FastAPI / SQLAlchemy / SQLite
- FFmpeg / FFprobe
- TransVLM V5（独立 Python 3.12 Runtime，当前正式 Shot Transition 模型）
- Source PTS 帧级边界落点
- Frame-exact Reference Clip

Frontend：
- Vue 3
- TypeScript
- Vue Router
- Vite 8

TransNetV2 / PySceneDetect 仍可能保留在 Legacy 代码或历史测试中，但不再是当前正式自动拉片入口。

## 快速运行

完整首次安装不要只看本节，请阅读 `docs/INSTALL_AND_RUN_WINDOWS.md`。

### 后端

```powershell
cd E:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

### 前端

```powershell
cd E:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

## TransVLM Runtime

首次安装：

```powershell
cd E:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

检查 Runtime：

```powershell
python -c "from engine.app.transvlm_runtime_v5 import runtime_status; import json; print(json.dumps(runtime_status(), ensure_ascii=False, indent=2))"
```

必须看到：

```text
ready = true
```

完整依赖、CUDA/cuDNN、Node、uv、模型下载及故障处理见安装手册。

## V2 本地数据

默认：

```text
data_v2/
├ studio_v2.sqlite3
├ models/
└ workspace/
```

可以设置：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

TransVLM 独立 Runtime 默认在：

```text
.runtime/TransVLM/
```

模型 Runtime 和业务数据都不应提交到 Git。

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

拉片任务会自动确保分析素材已经准备；内部输出包括 Proxy / Audio / Media Info。

### F04 / Shot V5 自动拉片

支持单集拉片 / 重新拉片和顺序批量拉片。

正式链路：

```text
Source Video
→ TransVLM transition segments
→ Source PTS
→ Shot boundaries
→ frame-exact Reference Clip
→ Current Shot Revision
```

每个 Shot 输出：
- start/end/duration；
- Reference Clip；
- Thumbnail。

Reference Clip 是后续视频重制的正式输入资产。

### 03 资产

当前资产工作区和历史 Evidence 仍保留，但人物身份策略正在重新规划。在新的资产方案稳定前，优先完成 Shot V5 的真实视频验收。

## 测试

V2 默认测试：

```powershell
python -m pytest engine/tests/v2 -q
```

当前拉片重点测试：

```powershell
python -m pytest engine/tests/v2/test_transvlm_shot_v5.py -q
python -m pytest engine/tests/v2/test_shot_v4_runtime_wiring.py -q
python -m pytest engine/tests/v2/test_shot_boundary_v4.py -q
```

真实 Windows 短剧视频仍是 Shot V5 的最终验收 Gate，重点检查：
- TransVLM Runtime；
- hard cut 是否漏检；
- 渐变转场；
- Shot 是否产生异常碎片；
- 相邻 Reference Clip 是否严格按帧所有权切分；
- OUT / NEXT IN 是否分别属于正确的左右镜头。

## Legacy

仓库里可能仍存在旧业务代码、旧模型入口和旧文档，以便必要时参考历史算法实现；它们不自动代表当前正式产品 Contract。正式安装运行以 `docs/INSTALL_AND_RUN_WINDOWS.md`、`AGENTS.md`、`SKILL.md` 和当前代码为准。
