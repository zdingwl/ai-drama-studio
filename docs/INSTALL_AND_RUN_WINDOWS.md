# AI Drama Studio — Windows 安装与运行手册

> 适用项目：`zdingwl/ai-drama-studio`
>
> 当前重点基线：Reference Video V2 / Shot V5 TransVLM-first。
>
> 本手册面向第一次拿到项目的 Windows 机器，也可作为日常启动、更新和故障排查手册。

---

## 1. 当前运行架构

项目当前使用两个相互隔离的 Python Runtime：

```text
AI Drama Studio
│
├─ .venv
│  ├─ FastAPI / SQLAlchemy / SQLite
│  ├─ FFmpeg 调度
│  ├─ Shot Revision / Reference Clip
│  └─ 现有业务后端
│
├─ frontend/
│  └─ Vue 3 + TypeScript + Vite 8
│
└─ .runtime/TransVLM/
   └─ inference/.venv
      ├─ Python 3.12
      ├─ PyTorch 2.9.1
      ├─ cuDNN 9.16+
      ├─ TransVLM-Qwen3-VL-4B-Instruct
      └─ NeuFlow v2
```

正式自动拉片链路：

```text
Source Video
→ TransVLM transition segments
→ Source PTS 帧级落点
→ Shot boundaries
→ frame-exact Reference Clip
→ Shot Revision Current
```

`TransNetV2 / PySceneDetect` 不再是当前正式自动拉片入口。

> 注意：`.runtime/TransVLM` 是独立模型 Runtime，不要把它的 torch / cuDNN 依赖直接安装进主工程 `.venv`。

---

## 2. 推荐机器环境

### 2.1 操作系统

推荐：

```text
Windows 10 / Windows 11 64-bit
PowerShell 5.1 或 PowerShell 7
```

PowerShell 7 体验更好，但不是强制要求。

### 2.2 NVIDIA GPU

TransVLM 当前要求 NVIDIA CUDA GPU。

先检查：

```powershell
nvidia-smi
```

必须能够正常打印 GPU、Driver Version 和显存信息。

安装脚本会根据 NVIDIA Driver 自动选择：

```text
Driver >= 570 → cu130
Driver < 570  → cu128
```

### 2.3 Python

新机器推荐安装 Python 3.12。

检查：

```powershell
python --version
py -0p
```

推荐能看到：

```text
Python 3.12.x
```

TransVLM 独立 Runtime 会由 `uv` 自动准备 Python 3.12，因此主机只要 `uv` 能正常工作即可。

### 2.4 Node.js

前端当前使用 Vite 8。

Vite 8 要求：

```text
Node.js 20.19+
或
Node.js 22.12+
```

推荐直接安装 Node.js 22 LTS。

检查：

```powershell
node --version
npm --version
```

### 2.5 FFmpeg

检查：

```powershell
ffmpeg -version
ffprobe -version
```

两个命令都必须能直接在 PowerShell 中运行。

### 2.6 Git

检查：

```powershell
git --version
```

### 2.7 uv

TransVLM 安装必须使用 `uv`。

检查：

```powershell
uv --version
```

如果没有安装：

```powershell
winget install --id=astral-sh.uv -e
```

安装完成后关闭当前 PowerShell，重新打开，再执行：

```powershell
uv --version
```

---

## 3. Windows 常用基础软件安装

已有的软件不要重复安装。

可以使用 `winget`：

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
```

FFmpeg 可以继续使用机器现有安装，只要：

```powershell
ffmpeg -version
ffprobe -version
```

能够成功即可。

NVIDIA Driver 建议使用当前显卡适配的正式驱动，不要为了项目手工安装一套系统 CUDA Toolkit；TransVLM Runtime 使用自己的 PyTorch CUDA wheel 和 cuDNN Python 包。

---

## 4. 获取 / 更新项目

### 4.1 第一次克隆

```powershell
cd E:\
git clone <项目仓库地址> ai-drama-studio
cd E:\ai-drama-studio
```

### 4.2 已有项目更新

```powershell
cd E:\ai-drama-studio
git pull
```

当前开发直接在 `main` 上进行，因此日常更新以 `git pull` 为主。

查看当前版本：

```powershell
git status
git log -5 --oneline
```

---

## 5. 安装主工程 Python 环境

> 如果当前 `.venv` 已经稳定运行，不需要仅为了 TransVLM 删除重建。TransVLM 使用独立 Runtime。

第一次安装推荐：

```powershell
cd E:\ai-drama-studio
py -3.12 -m venv .venv
```

如果 PowerShell 阻止激活脚本，可以只对当前窗口放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

激活环境：

```powershell
.\.venv\Scripts\Activate.ps1
```

升级 pip：

```powershell
python -m pip install --upgrade pip
```

安装后端依赖：

```powershell
pip install -r engine\requirements.txt
```

验证关键包：

```powershell
python -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

当前拉片的 TransVLM GPU 推理不依赖主 `.venv` 的 torch CUDA 状态，因此即使主环境的 torch 是 CPU build，也不会阻止 TransVLM Shot V5 运行。

---

## 6. 安装 TransVLM Runtime

### 6.1 安装前检查

在项目根目录执行：

```powershell
cd E:\ai-drama-studio
Get-Command git,uv,ffmpeg,nvidia-smi
```

应该能够找到：

```text
git.exe
uv.exe
ffmpeg.exe
nvidia-smi.exe
```

如果 `uv` 缺失：

```powershell
winget install --id=astral-sh.uv -e
```

然后重新打开 PowerShell。

### 6.2 执行自动安装

```powershell
cd E:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

脚本会自动：

```text
1. 检查 git / uv / ffmpeg / nvidia-smi
2. 克隆或更新官方 HeyGen TransVLM
3. 检测 NVIDIA Driver
4. 自动选择 cu128 / cu130
5. 安装 Python 3.12
6. 创建 TransVLM 独立 .venv
7. 安装官方 HuggingFace inference 依赖
8. 固定 cuDNN >= 9.16
9. 下载 TransVLM checkpoint
10. 下载 NeuFlow v2 权重
11. 执行 infer_video.py --help 自检
```

模型为多 GB 文件，第一次下载需要稳定网络和足够磁盘空间。

### 6.3 正常完成标志

最后应该出现类似：

```text
[TransVLM] READY
  Python: E:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe
  Checkpoint: E:\ai-drama-studio\.runtime\TransVLM\inference\pretrained\TransVLM-v1
  Backend: hf
  CUDA group: cu128
```

或：

```text
CUDA group: cu130
```

### 6.4 检查项目是否能识别 Runtime

激活主 `.venv` 后执行：

```powershell
python -c "from engine.app.transvlm_runtime_v5 import runtime_status; import json; print(json.dumps(runtime_status(), ensure_ascii=False, indent=2))"
```

正常应该包含：

```json
{
  "ready": true,
  "profile": "TransVLM-Qwen3-VL-4B-Instruct",
  "backend": "hf",
  "device": "cuda:0",
  "missing": []
}
```

如果 `ready=false`，先解决 `missing` 中列出的项目，不要启动正式拉片。

---

## 7. 安装前端

打开一个 PowerShell：

```powershell
cd E:\ai-drama-studio\frontend
npm install
```

验证 TypeScript：

```powershell
npm run typecheck
```

可选完整构建检查：

```powershell
npm run build
```

---

## 8. 第一次启动项目

推荐使用两个 PowerShell 窗口。

### 8.1 PowerShell A：启动后端

```powershell
cd E:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

正常会看到 Uvicorn 正在监听：

```text
http://127.0.0.1:8000
```

### 8.2 后端健康检查

另开 PowerShell：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

应该返回类似：

```text
status       : ok
architecture : reference-video-v2
app_version  : 2.4.1
```

### 8.3 PowerShell B：启动前端

```powershell
cd E:\ai-drama-studio\frontend
npm run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 请求代理到：

```text
http://127.0.0.1:8000
```

浏览器打开：

```text
http://127.0.0.1:5173
```

---

## 9. 当前正确的首次业务验收顺序

目前先验收拉片，不要同时用资产提取结果判断 Shot V5 是否正确。

推荐顺序：

```text
1. 新建项目
2. 导入 1 集短视频
3. 点击单集拉片
4. 等待 TransVLM 完成
5. 检查 Shot 数量
6. 检查明显 hard cut 是否漏检
7. 检查是否存在大量极短碎片 Shot
8. 检查每个公共边界的 OUT / NEXT IN
9. 确认 Reference Clip 正确后再批量拉片
```

当前拉片硬约束：

```text
左 Shot  = [start_frame, cut_frame)
右 Shot  = [cut_frame, next_cut_frame)
```

相邻 Shot 不应该共享 Cut frame。

例如：

```text
客厅 / 蓝花
↓ CUT
年轻女性
```

应该看到：

```text
SHOT 0001 OUT = 客厅 / 蓝花最后一帧
SHOT 0002 IN  = 年轻女性第一帧
```

---

## 10. 拉片相关测试

激活主 `.venv`：

```powershell
cd E:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
```

### 10.1 TransVLM V5 Segment 语义

```powershell
python -m pytest engine/tests/v2/test_transvlm_shot_v5.py -q
```

该测试覆盖：

```text
TransVLM 秒 → 微秒
零长度 hard cut 保留
hard cut → Source frame break
渐变转场 → segment midpoint
重复 transition 去重
超长 transition REVIEW
```

### 10.2 正式入口接线

```powershell
python -m pytest engine/tests/v2/test_shot_v4_runtime_wiring.py -q
```

虽然测试文件仍保留历史名称 `v4`，当前断言的是正式 `media_v2.detect_episode_shots` 必须接到 TransVLM V5。

### 10.3 Reference Clip 帧所有权

```powershell
python -m pytest engine/tests/v2/test_shot_boundary_v4.py -q
```

### 10.4 当前 V2 全量测试

```powershell
python -m pytest engine/tests/v2 -q
```

---

## 11. 日常启动

电脑重启后，一般不需要重新安装任何模型。

### 后端

```powershell
cd E:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

另开窗口：

```powershell
cd E:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

---

## 12. 日常更新项目

停止前后端后：

```powershell
cd E:\ai-drama-studio
git pull
```

如果 `engine/requirements.txt` 有变化：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r engine\requirements.txt
```

如果 `frontend/package.json` 或 lockfile 有变化：

```powershell
cd frontend
npm install
```

如果 TransVLM 安装脚本或官方 Runtime 要求发生变化，再执行：

```powershell
cd E:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

脚本发现官方仓库已经存在时会尝试 fast-forward 更新，而不是重新建立一个重复 Runtime。

---

## 13. 本地数据目录

默认业务数据：

```text
data_v2/
├─ studio_v2.sqlite3
├─ models/
└─ workspace/
```

TransVLM Runtime：

```text
.runtime/TransVLM/
```

这些目录都不应该提交到 Git。

### 13.1 修改业务数据目录

可以在启动后端前：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

然后再启动：

```powershell
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

注意：环境变量只对当前 PowerShell 进程及其子进程生效。

---

## 14. TransVLM 环境变量

正常安装不需要手工配置。

高级调试时可以覆盖：

```powershell
$env:AI_DRAMA_TRANSVLM_INFERENCE="E:\somewhere\TransVLM\inference"
$env:AI_DRAMA_TRANSVLM_PYTHON="E:\somewhere\.venv\Scripts\python.exe"
$env:AI_DRAMA_TRANSVLM_CKPT="E:\models\TransVLM-v1"
$env:AI_DRAMA_TRANSVLM_DEVICE="cuda:0"
```

不需要覆盖时不要设置这些变量。

---

## 15. 常见故障排查

### 15.1 `uv` 无法识别

错误：

```text
无法将“uv”项识别为 cmdlet...
```

处理：

```powershell
winget install --id=astral-sh.uv -e
```

关闭并重新打开 PowerShell：

```powershell
uv --version
where.exe uv
```

### 15.2 TransVLM 安装脚本提示缺命令

执行：

```powershell
Get-Command git,uv,ffmpeg,nvidia-smi
```

缺哪个先安装哪个。

### 15.3 `nvidia-smi` 不工作

这是 NVIDIA Driver / 系统问题，不是 Python 项目问题。

先修复 NVIDIA Driver，直到：

```powershell
nvidia-smi
```

可以正常显示 GPU。

### 15.4 cuDNN 版本不足

安装脚本会检查：

```text
cuDNN >= 91600
```

如果失败，不要继续跑模型。

重新执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

并保留完整错误信息。

### 15.5 TransVLM Runtime `ready=false`

执行：

```powershell
python -c "from engine.app.transvlm_runtime_v5 import runtime_status; import json; print(json.dumps(runtime_status(), ensure_ascii=False, indent=2))"
```

重点检查：

```text
missing
config.inference_root
config.python_executable
config.checkpoint_dir
```

### 15.6 拉片时仍然看到 `transnetv2_pytorch` Warning

当前正式拉片已经是 TransVLM V5。

如果点击“重新自动拉片”后仍持续看到 TransNetV2 推理日志，优先检查：

```text
1. 本机是否已经 git pull 到最新 main
2. 旧 Uvicorn 是否没有真正退出
3. 是否启动了另一个旧项目目录
4. 是否存在多个 Python / uvicorn 进程
```

建议完全关闭后端窗口，再重新启动。

检查代码版本：

```powershell
git log -10 --oneline
```

### 15.7 后端 8000 端口被占用

检查：

```powershell
netstat -ano | findstr :8000
```

找到 PID 后确认是不是旧 Uvicorn。

### 15.8 前端 5173 端口被占用

检查：

```powershell
netstat -ano | findstr :5173
```

Vite 默认会尝试下一个端口，但当前后端 CORS 只明确允许 `localhost:5173` 和 `127.0.0.1:5173`，开发时最好释放 5173 后再启动。

### 15.9 `npm run dev` 提示 Node 版本太旧

执行：

```powershell
node --version
```

Vite 8 要求：

```text
20.19+
或 22.12+
```

推荐升级 Node 22 LTS。

### 15.10 FFmpeg / FFprobe 找不到

执行：

```powershell
where.exe ffmpeg
where.exe ffprobe
```

确认安装目录已经加入 PATH。

### 15.11 `Activate.ps1` 被执行策略阻止

只对当前窗口临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

再执行：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 15.12 前端能打开但 API 报错

先检查后端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果健康检查失败，先解决后端，不要从 Vue 页面继续排查。

---

## 16. 收集故障日志的方法

如果需要提交问题，优先提供：

```text
1. 执行的完整命令
2. 错误发生前后至少 50~100 行日志
3. git log -5 --oneline
4. python --version
5. node --version
6. uv --version
7. ffmpeg -version 的第一屏
8. nvidia-smi
9. TransVLM runtime_status()
```

TransVLM 安装失败时，不要只截最后一句 `FAILED`，应保留前面的 Python / CUDA / cuDNN / HuggingFace 错误。

---

## 17. 推荐的安装后验收清单

完成首次安装后依次确认：

```text
[ ] git --version
[ ] python --version
[ ] node --version
[ ] npm --version
[ ] uv --version
[ ] ffmpeg -version
[ ] ffprobe -version
[ ] nvidia-smi
[ ] 主 .venv 安装完成
[ ] TransVLM setup 输出 READY
[ ] runtime_status.ready == true
[ ] npm install 完成
[ ] npm run typecheck 通过
[ ] /api/health 返回 status=ok
[ ] 浏览器可打开 127.0.0.1:5173
[ ] TransVLM V5 测试通过
[ ] 单集真实视频拉片完成
[ ] Shot OUT / NEXT IN 边界验收通过
```

只有最后几项真实视频验收通过后，才把这台机器视为“拉片生产环境已准备好”。

---

## 18. 最短日常启动命令

### 窗口 A — 后端

```powershell
cd E:\ai-drama-studio
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

### 窗口 B — 前端

```powershell
cd E:\ai-drama-studio\frontend
npm run dev
```

### 浏览器

```text
http://127.0.0.1:5173
```
