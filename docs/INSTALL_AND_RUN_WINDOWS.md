# AI Drama Studio — Windows 裸机安装与运行手册

> 适用项目：`zdingwl/ai-drama-studio`
>
> 当前正式拉片基线：Shot V5 / TransVLM-first / Source PTS frame ownership。
>
> **本手册从“刚装好的 Windows，只有浏览器和系统自带 Windows PowerShell”开始。**
>
> 如果 `git`、`python`、`node`、`npm`、`uv`、`ffmpeg` 一个都不能执行，这是正常起点。

---

# 0. 裸机安装总顺序

第一次安装按这个顺序，不要跳步骤：

```text
Windows / 浏览器 / PowerShell
↓
NVIDIA 驱动
↓
App Installer / winget
↓
Git / Node.js / uv / FFmpeg
↓
关闭并重新打开 PowerShell
↓
克隆 AI Drama Studio
↓
uv 安装 Python 3.12
↓
uv 创建主工程 .venv
↓
uv pip 安装后端依赖
↓
npm 安装前端依赖
↓
setup_transvlm_runtime.ps1
↓
check_transvlm_runtime.ps1
↓
启动后端
↓
启动前端
↓
单集真实视频拉片验收
```

如果某一步提示“命令不存在”，先解决当前步骤，不要继续往下执行。

---

# 1. 建议硬件与系统

## 1.1 Windows

推荐：

```text
Windows 10 64-bit
或
Windows 11 64-bit
```

系统自带 Windows PowerShell 5.1 可以完成安装。

## 1.2 NVIDIA GPU

当前正式 TransVLM 拉片要求 NVIDIA GPU。

建议至少：

```text
8 GB VRAM
```

8 GB 显存可以运行，但 TransVLM 会非常吃显存、内存和磁盘。

## 1.3 系统内存

建议：

```text
最低：32 GB
推荐：64 GB
```

TransVLM 官方 whole-video NeuFlow 会处理整段视频，长视频可能占用大量 RAM。

## 1.4 磁盘

建议至少预留：

```text
50 GB 可用空间
```

推荐项目和 `data_v2` 放 SSD / NVMe。

---

# 2. 安装 NVIDIA 驱动

浏览器打开 NVIDIA 官方驱动下载页面：

```text
https://www.nvidia.com/Download/index.aspx
```

安装与你显卡对应的正式驱动，完成后建议重启 Windows。

重新打开 PowerShell：

```powershell
nvidia-smi
```

必须能看到 GPU、Driver Version、CUDA Version 等信息。

如果 `nvidia-smi` 无法识别，先修好 NVIDIA 驱动，不要继续安装 TransVLM。

> 不需要为了本项目另外安装系统 CUDA Toolkit。TransVLM 使用隔离 Runtime 中的 PyTorch CUDA 依赖。

---

# 3. 让 Windows 具备 winget

执行：

```powershell
winget --version
```

如果能显示版本，直接进入下一章。

如果提示无法识别：

```text
Microsoft Store
→ 搜索 App Installer / 应用安装程序
→ 发布者 Microsoft Corporation
→ 安装或更新
```

然后关闭所有 PowerShell，再重新打开。

## 3.1 msstore 源证书错误

某些机器会出现：

```text
搜索源时失败: msstore
0x8a15005e : 服务器证书与任何预期值都不匹配
```

这不代表整个 winget 坏了。

安装项目依赖时显式指定社区源：

```powershell
--source winget
```

例如：

```powershell
winget install --id astral-sh.uv -e --source winget
```

不需要为了安装本项目先修复 `msstore` 源。

---

# 4. 安装基础工具

## 4.1 Git

```powershell
winget install --id Git.Git -e --source winget
```

## 4.2 Node.js LTS

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

前端使用 Vite 8，需要：

```text
Node 20.19+
或
Node 22.12+
```

## 4.3 uv

```powershell
winget install --id astral-sh.uv -e --source winget
```

`uv` 负责：

```text
Python 3.12
主工程 .venv
TransVLM Python 3.12 Runtime
Python 包安装
```

裸机不需要先自己安装 Python。

## 4.4 FFmpeg

推荐安装 Shared 版：

```powershell
winget install --id Gyan.FFmpeg.Shared -e --source winget
```

如果 WinGet 显示：

```text
找到已安装的现有包
找不到可用的升级
```

不代表安装失败。

当前 `setup_transvlm_runtime.ps1` 会：

```text
优先扫描本机已有兼容 Shared FFmpeg
↓
找到就复用
↓
找不到则准备项目自己的 pinned Shared FFmpeg Runtime
↓
实际导入 TorchCodec VideoDecoder 验证
```

不要为了 WinGet 的“无法升级”提示反复卸载 FFmpeg。

## 4.5 Microsoft Visual C++ Runtime

浏览器打开：

```text
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

安装 Microsoft Visual C++ 2015-2022 x64 Redistributable。

---

# 5. 安装基础工具后必须重新打开 PowerShell

安装 Git / Node / uv / FFmpeg 后：

```text
关闭当前 PowerShell
关闭其他旧 PowerShell
重新打开一个新的 PowerShell
```

然后验证：

```powershell
git --version
node --version
npm --version
uv --version
ffmpeg -version
ffprobe -version
nvidia-smi
```

也可以查看路径：

```powershell
where.exe git
where.exe node
where.exe npm
where.exe uv
where.exe ffmpeg
where.exe ffprobe
where.exe nvidia-smi
```

如果某个命令完全找不到，先解决安装/PATH，不要继续。

---

# 6. 不使用 winget 的手工安装方式

如果 winget 完全不可用，可以浏览器安装。

Git：

```text
https://git-scm.com/download/win
```

Node.js LTS：

```text
https://nodejs.org/en/download
```

uv：

```text
https://docs.astral.sh/uv/getting-started/installation/
```

uv 官方 PowerShell 安装命令：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

FFmpeg Shared：

```text
https://www.gyan.dev/ffmpeg/builds/
```

如果手工下载，必须是 **full shared build**。

正确 `bin` 目录不仅有：

```text
ffmpeg.exe
ffprobe.exe
```

还应该有：

```text
avcodec-*.dll
avformat-*.dll
avutil-*.dll
```

---

# 7. 获取 AI Drama Studio

推荐目录：

```text
D:\ai-drama-studio
```

第一次克隆：

```powershell
cd D:\
git clone https://github.com/zdingwl/ai-drama-studio.git
cd D:\ai-drama-studio
```

验证：

```powershell
git status
git log -5 --oneline
```

如果暂时没有 Git，也可以浏览器打开仓库 → `Code` → `Download ZIP`，但长期更新仍推荐使用 Git。

---

# 8. 用 uv 安装 Python 3.12

```powershell
cd D:\ai-drama-studio
uv python install 3.12
```

验证：

```powershell
uv python list
```

应该能看到 Python 3.12。

---

# 9. 创建主工程 .venv

执行：

```powershell
cd D:\ai-drama-studio
uv venv .venv --python 3.12
```

激活：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

验证：

```powershell
python --version
```

应该是 Python 3.12.x。

## 9.1 uv venv 默认不保证带 pip

下面这个报错不表示 `.venv` 损坏：

```text
D:\ai-drama-studio\.venv\Scripts\python.exe: No module named pip
```

本项目主环境统一使用：

```text
uv pip
```

不要把 `python -m pip` 是否存在当成环境是否正常的判断标准。

## 9.2 如果 PowerShell 禁止 Activate.ps1

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

该设置只影响当前 PowerShell 窗口。

## 9.3 如果确实需要传统 pip

项目正常运行不需要这一步。

如果第三方工具明确要求 `.venv` 内存在 pip：

```powershell
uv pip install --python .\.venv\Scripts\python.exe pip
```

或者重新创建带 seed 包的环境：

```powershell
uv venv .venv --python 3.12 --seed
```

---

# 10. 安装主工程后端依赖

不要执行：

```powershell
python -m pip install --upgrade pip
pip install -r engine\requirements.txt
```

裸机标准安装统一执行：

```powershell
cd D:\ai-drama-studio
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

安装后验证：

```powershell
.\.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

应输出：

```text
backend imports OK
```

> 主工程 `.venv` 和 TransVLM `.runtime\TransVLM\inference\.venv` 是两个独立 Runtime，不要混装依赖。

---

# 11. 安装前端依赖

```powershell
cd D:\ai-drama-studio\frontend
npm install
```

验证：

```powershell
npm run typecheck
```

可选完整构建：

```powershell
npm run build
```

---

# 12. 安装 TransVLM Runtime

这是当前正式拉片最重要的一步。

先检查：

```powershell
cd D:\ai-drama-studio
Get-Command git,uv,ffmpeg,nvidia-smi
```

执行自动安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

脚本会自动完成：

```text
1. 检查 git / uv / nvidia-smi
2. 克隆或更新 HeyGen 官方 TransVLM
3. 根据 NVIDIA Driver 选择 CUDA group
4. 用 uv 准备 Python 3.12
5. 创建 TransVLM 独立 .venv
6. 安装官方 inference 依赖
7. 安装 cuDNN 9.16
8. Windows 下将正确 cuDNN DLL stage 到隔离 torch runtime
9. 检查本机兼容 Shared FFmpeg
10. 找不到时准备项目本地 pinned Shared FFmpeg Runtime
11. 注入 Shared FFmpeg + torch\lib 到 PATH
12. 实际导入 TorchCodec VideoDecoder
13. 下载 TransVLM Qwen3-VL 4B checkpoint
14. 下载 NeuFlow v2 权重
15. 执行 infer_video.py --help 自检
```

第一次执行会下载多 GB 文件，耗时较长。

正常最终应看到：

```text
[TransVLM] READY
```

---

# 13. TransVLM 安装后正确的自检方式

## 13.1 不要直接裸跑 TorchCodec

下面这种命令**不作为项目标准自检方式**：

```powershell
D:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe -c "from torchcodec.decoders import VideoDecoder; print('torchcodec=OK')"
```

原因是 Windows DLL 搜索依赖当前进程 `PATH`。

正式后台启动 TransVLM 时会自动把：

```text
Shared FFmpeg\bin
+
TransVLM\.venv\Lib\site-packages\torch\lib
```

放到子进程 `PATH` 前面。

裸跑 `python.exe` 没有这一步，因此即使 Runtime 安装正确，也可能报：

```text
RuntimeError: Could not load libtorchcodec
```

## 13.2 使用项目提供的 Runtime 自检脚本

统一执行：

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\check_transvlm_runtime.ps1
```

这个脚本会使用和正式后台相同的 DLL 搜索路径，并检查：

```text
Shared FFmpeg bin 是否存在
ffmpeg.exe / ffprobe.exe
avcodec / avformat / avutil DLL
PyTorch CUDA
GPU
cuDNN
TorchCodec VideoDecoder
infer_video.py
```

成功时应看到：

```text
[TransVLM] RUNTIME CHECK PASSED
  CUDA/cuDNN: OK
  TorchCodec: OK
  FFmpeg shared DLLs: OK
  infer_video.py: OK
```

## 13.3 项目 Runtime 状态

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\python.exe -c "from engine.app.transvlm_runtime_v5 import runtime_status; import json; print(json.dumps(runtime_status(), ensure_ascii=False, indent=2))"
```

正常应该包含：

```json
{
  "ready": true,
  "backend": "hf",
  "device": "cuda:0",
  "missing": []
}
```

注意：`runtime_status()` 主要检查路径和配置；真正 CUDA / TorchCodec 动态库验证以 `check_transvlm_runtime.ps1` 为准。

---

# 14. 启动后端

PowerShell A：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

---

# 15. 启动前端

PowerShell B：

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

浏览器打开：

```text
http://127.0.0.1:5173
```

---

# 16. 第一次业务验收

第一次只导入 1 集短视频。

正确顺序：

```text
1. 新建项目
2. 导入 1 个视频
3. 点击单集拉片
4. 等待 TransVLM 完成
5. 看 Shot 数量
6. 检查明显 Hard Cut 是否漏切
7. 检查是否产生大量碎片 Shot
8. 检查相邻 Shot 的 OUT / NEXT IN
9. 确认拉片结果可用
10. 再批量处理其他剧集
```

当前正式链路：

```text
Source Video
↓
25fps / resize
↓
whole-video NeuFlow
↓
RGB + Optical Flow
↓
Qwen3-VL 4B TransVLM
↓
Transition Segments
↓
Source PTS 精确落帧
↓
Shot Boundaries
↓
Frame-exact Reference Clips
```

---

# 17. TransVLM 运行时为什么很重

运行期间出现下面现象通常是正常的：

```text
内存占用很高
磁盘持续读写
GPU 显存接近满
GPU 利用率经常 90%~100%
某些阶段 GPU 利用率突然降低后又升高
```

查看 GPU：

```powershell
nvidia-smi -l 1
```

如果能看到 TransVLM Python 进程，并且 GPU-Util / 显存持续有活动，通常说明模型仍在工作。

查看 Python CPU / RAM：

```powershell
Get-Process python |
Sort-Object CPU -Descending |
Select-Object Id,CPU,@{Name='RAM_GB';Expression={[math]::Round($_.WorkingSet64 / 1GB, 2)}},StartTime
```

---

# 18. 拉片进度说明

当前 V5 会尽量显示：

```text
准备 25fps 模型输入
↓
缩放模型输入
↓
NeuFlow 整集光流
↓
窗口计划
↓
Qwen3-VL window x / N
↓
合并 Transition
↓
Source PTS 落帧
↓
Reference Clip
```

whole-video NeuFlow 官方实现本身没有细粒度逐 batch 进度，因此这一阶段可能持续较久。

只要 GPU / CPU / RAM / Disk 仍有活动，就不要仅因为百分比短时间不动强制结束任务。

---

# 19. 日常启动

电脑重启后不需要重新安装模型。

后端：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

---

# 20. 更新项目

停止前后端后：

```powershell
cd D:\ai-drama-studio
git pull
```

如果后端依赖变化：

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

如果前端依赖变化：

```powershell
cd D:\ai-drama-studio\frontend
npm install
```

如果 TransVLM Runtime 要求变化：

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_transvlm_runtime.ps1
```

---

# 21. 常见问题：No module named pip

报错：

```text
No module named pip
```

处理：

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

不需要删除 `.venv`。

---

# 22. 常见问题：cuDNN = 91002

如果安装时报：

```text
TransVLM requires cuDNN >= 9.16; detected 91002
```

当前安装脚本会在隔离 TransVLM Runtime 中把正确 9.16 DLL stage 到 `torch\lib`。

处理：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

不要手工修改系统 CUDA / cuDNN。

---

# 23. 常见问题：Could not load libtorchcodec

先区分两种情况。

## 情况 A：你是直接裸跑 TransVLM python.exe

例如：

```powershell
...\TransVLM\inference\.venv\Scripts\python.exe -c "from torchcodec.decoders import VideoDecoder"
```

这条命令没有自动注入 Shared FFmpeg DLL 路径，因此可能失败。

正确验证：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\check_transvlm_runtime.ps1
```

## 情况 B：setup 或正式拉片也失败

重新执行：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_transvlm_runtime.ps1
```

如果仍失败，把 `check_transvlm_runtime.ps1` 的完整输出保存下来继续排查。

---

# 24. 常见问题：端口被占用

后端：

```powershell
netstat -ano | findstr :8000
```

前端：

```powershell
netstat -ano | findstr :5173
```

---

# 25. 一台全新电脑的最短安装清单

## A. 浏览器 / GUI

```text
1. 安装 NVIDIA 驱动
2. 安装/更新 Microsoft App Installer
3. 安装 Microsoft Visual C++ 2015-2022 x64 Runtime
4. 重启电脑
```

## B. PowerShell

```powershell
winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
winget install --id astral-sh.uv -e --source winget
winget install --id Gyan.FFmpeg.Shared -e --source winget
```

关闭 PowerShell，再重新打开。

## C. 克隆项目

```powershell
cd D:\
git clone https://github.com/zdingwl/ai-drama-studio.git
cd D:\ai-drama-studio
```

## D. Python / 后端

```powershell
uv python install 3.12
uv venv .venv --python 3.12
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
.\.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

## E. 前端

```powershell
cd D:\ai-drama-studio\frontend
npm install
```

## F. TransVLM

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_transvlm_runtime.ps1
```

必须看到：

```text
[TransVLM] READY
[TransVLM] RUNTIME CHECK PASSED
```

## G. 启动

后端：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

---

# 26. 安装完成验收清单

```text
[ ] nvidia-smi 正常
[ ] winget 正常
[ ] Git 正常
[ ] Node.js / npm 正常
[ ] uv 正常
[ ] ffmpeg / ffprobe 正常
[ ] 项目已克隆
[ ] uv Python 3.12 正常
[ ] 主 .venv 正常
[ ] backend imports OK
[ ] npm install 完成
[ ] setup_transvlm_runtime.ps1 输出 READY
[ ] check_transvlm_runtime.ps1 输出 RUNTIME CHECK PASSED
[ ] CUDA = True
[ ] cuDNN >= 91600
[ ] TorchCodec = OK
[ ] runtime_status ready=true
[ ] FastAPI :8000 正常
[ ] Vite :5173 正常
[ ] 浏览器可以打开项目
[ ] 单集真实视频可以进入 TransVLM 拉片
```

任何一项不满足，都先修对应环境，不要跳着继续。

---

# 27. 当前运行架构

```text
AI Drama Studio
│
├─ .venv
│  ├─ FastAPI
│  ├─ SQLAlchemy / SQLite
│  ├─ FFmpeg 调度
│  └─ Shot / Revision API
│
├─ frontend\
│  └─ Vue 3 + TypeScript + Vite
│
└─ .runtime\TransVLM\inference\.venv
   ├─ Python 3.12
   ├─ PyTorch CUDA
   ├─ cuDNN 9.16+
   ├─ TorchCodec
   ├─ NeuFlow v2
   └─ TransVLM-Qwen3-VL-4B-Instruct
```

不要为了“统一环境”把 TransVLM 的 torch / cuDNN 直接塞进主 `.venv`。

当前正式拉片：

```text
Source Video
→ TransVLM transition segments
→ Source PTS frame resolution
→ Shot boundaries
→ frame-exact Reference Clip
→ Current Shot Revision
```

`TransNetV2 / PySceneDetect` 不再是当前正式自动拉片入口。
