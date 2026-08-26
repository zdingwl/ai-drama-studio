# AI Drama Studio — Windows 裸机安装与运行手册

> 适用项目：`zdingwl/ai-drama-studio`
>
> 当前拉片基线：Reference Video V2 / Shot V5 / TransVLM-first。
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
CUDA / cuDNN / TorchCodec 检查
↓
启动后端
↓
启动前端
↓
单集真实视频拉片验收
```

如果某一步提示“命令不存在”，先解决该步骤，不要继续往下执行。

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

TransVLM 官方 whole-video NeuFlow 会一次性处理完整视频，长视频可能占用大量 RAM。

## 1.4 磁盘

建议至少预留：

```text
50 GB 可用空间
```

推荐项目和 `data_v2` 放 SSD / NVMe。

---

# 2. 安装 NVIDIA 驱动

新装 Windows 先安装显卡驱动。

浏览器打开 NVIDIA 官方驱动下载页面：

```text
https://www.nvidia.com/Download/index.aspx
```

安装与你显卡对应的正式驱动，安装完成后建议重启。

重新打开 PowerShell：

```powershell
nvidia-smi
```

必须能看到 GPU、Driver Version、CUDA Version 等信息。

如果 `nvidia-smi` 无法识别，先修好 NVIDIA 驱动，不要继续安装 TransVLM。

> 不需要为了本项目另外安装系统 CUDA Toolkit。TransVLM 使用隔离 Runtime 中的 PyTorch CUDA 依赖。

---

# 3. 让 Windows 具备 winget

先执行：

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

然后：

```text
关闭所有 PowerShell
重新打开 PowerShell
```

再次执行：

```powershell
winget --version
```

## 3.1 msstore 源报证书错误怎么办

某些机器会出现：

```text
搜索源时失败: msstore
0x8a15005e : 服务器证书与任何预期值都不匹配
```

这不代表整个 winget 坏了。

如果输出同时显示包可以从 `winget` 源找到，安装时显式指定：

```powershell
--source winget
```

例如：

```powershell
winget install --id astral-sh.uv -e --source winget
```

项目基础工具安装都建议显式使用 `--source winget`，这样不会被坏掉的 `msstore` 源阻塞。

---

# 4. 安装基础工具

以下命令在 PowerShell 中逐个执行。

## 4.1 Git

```powershell
winget install --id Git.Git -e --source winget
```

## 4.2 Node.js LTS

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget
```

前端使用 Vite 8，Node.js 需要满足：

```text
Node 20.19+
或
Node 22.12+
```

推荐使用当前 Node.js LTS。

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

所以裸机不需要先自己安装 Python。

## 4.4 FFmpeg

推荐直接安装 Shared 版：

```powershell
winget install --id Gyan.FFmpeg.Shared -e --source winget
```

如果 WinGet 显示：

```text
找到已安装的现有包
找不到可用的升级
```

不代表 FFmpeg 不能使用。

当前 `setup_transvlm_runtime.ps1` 会：

```text
优先扫描本机已有兼容 Shared FFmpeg
↓
找到就直接复用
↓
找不到时自动准备项目自己的 pinned Shared FFmpeg Runtime
↓
实际导入 TorchCodec VideoDecoder 验证
```

因此不要为了 WinGet 的“无法升级”提示反复卸载/重装 FFmpeg。

## 4.5 Microsoft Visual C++ Runtime

PyTorch / TorchCodec 等 Windows DLL 依赖 Microsoft Visual C++ Runtime。

浏览器打开：

```text
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

下载并安装 Microsoft Visual C++ 2015-2022 x64 Redistributable。

---

# 5. 基础工具安装完成后必须重新打开 PowerShell

安装 Git / Node / uv / FFmpeg 后：

```text
关闭当前 PowerShell
关闭其他旧 PowerShell
重新打开一个新的 PowerShell
```

然后逐个验证：

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

如果某个命令完全找不到，先解决该软件安装/PATH，不要继续。

---

# 6. 不使用 winget 的手工安装方式

如果 winget 完全不可用，可以用浏览器安装。

## Git

```text
https://git-scm.com/download/win
```

## Node.js LTS

```text
https://nodejs.org/en/download
```

## uv

```text
https://docs.astral.sh/uv/getting-started/installation/
```

也可以使用 uv 官方 PowerShell 安装命令：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## FFmpeg Shared

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

安装后都要关闭 PowerShell，再重新打开。

---

# 7. 获取 AI Drama Studio

推荐目录：

```text
D:\ai-drama-studio
```

如果没有 D 盘，可以改成 C 盘或其他 SSD。

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

如果暂时没有 Git，也可以浏览器打开仓库 → `Code` → `Download ZIP`，但长期更新仍建议使用 Git。

---

# 8. 用 uv 安装 Python 3.12

进入项目：

```powershell
cd D:\ai-drama-studio
```

安装：

```powershell
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

创建成功后应该存在：

```text
D:\ai-drama-studio\.venv\
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

## 9.1 重要：uv venv 默认不保证带 pip

`uv venv` 创建的是正常 Python 虚拟环境，但默认**不要求环境内部存在传统 `pip` 模块**。

因此下面这个报错并不表示 `.venv` 损坏：

```text
D:\ai-drama-studio\.venv\Scripts\python.exe: No module named pip
```

本项目主环境统一使用：

```text
uv pip
```

不要把 `python -m pip` 是否存在当成环境是否正常的判断标准。

## 9.2 如果 PowerShell 禁止执行 Activate.ps1

当前窗口临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

该设置只影响当前 PowerShell 窗口。

## 9.3 如果确实需要传统 pip

项目正常运行不需要这一步。

如果第三方工具明确要求 `.venv` 内存在 pip，可以执行：

```powershell
uv pip install --python .\.venv\Scripts\python.exe pip
```

然后：

```powershell
.\.venv\Scripts\python.exe -m pip --version
```

另一种方式是重新创建带 seed 包的环境：

```powershell
uv venv .venv --python 3.12 --seed
```

但对 AI Drama Studio 默认安装流程没有必要。

---

# 10. 安装主工程后端依赖

**不要执行：**

```powershell
python -m pip install --upgrade pip
pip install -r engine\requirements.txt
```

裸机标准安装统一执行：

```powershell
cd D:\ai-drama-studio
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

即使 `.venv` 没有 `pip` 模块，这条命令也可以正常安装依赖。

安装完成后验证：

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

打开新的 PowerShell：

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

如果 `npm` 无法识别，重新检查：

```powershell
node --version
npm --version
where.exe node
where.exe npm
```

---

# 12. 安装 TransVLM Runtime

这是当前正式拉片最重要的一步。

先确认：

```powershell
cd D:\ai-drama-studio
Get-Command git,uv,ffmpeg,nvidia-smi
```

四个命令必须全部找到。

执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

脚本会自动完成：

```text
1. 检查 git / uv / ffmpeg / nvidia-smi
2. 克隆或更新 HeyGen 官方 TransVLM
3. 根据 NVIDIA Driver 选择 CUDA group
4. 用 uv 准备 Python 3.12
5. 创建 TransVLM 独立 .venv
6. 安装官方 inference 依赖
7. 安装 cuDNN 9.16
8. Windows 下将正确 cuDNN DLL stage 到隔离 torch runtime
9. 检查本机兼容 Shared FFmpeg
10. 找不到时准备项目本地 pinned Shared FFmpeg Runtime
11. 验证 TorchCodec VideoDecoder
12. 下载 TransVLM Qwen3-VL 4B checkpoint
13. 下载 NeuFlow v2 权重
14. 执行 infer_video.py --help 自检
```

第一次执行会下载多 GB 文件，耗时较长。

正常最终应看到：

```text
[TransVLM] READY
```

并包含类似：

```text
Python: ...\.runtime\TransVLM\inference\.venv\Scripts\python.exe
Checkpoint: ...\pretrained\TransVLM-v1
Backend: hf
CUDA group: cu128 / cu130
Shared FFmpeg: ...
```

---

# 13. TransVLM 安装后检查

## 13.1 CUDA / cuDNN

```powershell
D:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe -c "import torch; print('cuda=',torch.cuda.is_available()); print('gpu=',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU'); print('torch=',torch.__version__); print('torch cuda=',torch.version.cuda); print('cudnn=',torch.backends.cudnn.version())"
```

至少应该满足：

```text
cuda= True
gpu= NVIDIA ...
cudnn= 91600 或更高
```

## 13.2 TorchCodec

```powershell
D:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe -c "from torchcodec.decoders import VideoDecoder; print('torchcodec=OK')"
```

应输出：

```text
torchcodec=OK
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
  "profile": "TransVLM-Qwen3-VL-4B-Instruct",
  "backend": "hf",
  "device": "cuda:0",
  "missing": []
}
```

`ready=false` 时先解决 `missing`，不要开始正式拉片。

---

# 14. 启动后端

PowerShell A：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

也可以完全不激活环境，直接：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\python.exe -m uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

如果端口被占用：

```powershell
netstat -ano | findstr :8000
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

Vite 会把 `/api` 代理到：

```text
http://127.0.0.1:8000
```

---

# 16. 第一次业务验收

第一次只测一集，不要同时测很多集，也不要用资产提取判断 Shot V5。

顺序：

```text
1. 新建项目
2. 导入 1 个真实短视频
3. 点击单集拉片
4. 等待 TransVLM 完成
5. 检查 Shot 数量
6. 检查明显 Hard Cut 是否漏切
7. 检查是否出现大量错误碎片 Shot
8. 检查相邻 Shot OUT / NEXT IN
9. 确认边界正确
10. 再批量处理其他剧集
```

正式链路：

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

# 17. TransVLM 运行时资源占用

运行期间以下情况可能是正常的：

```text
RAM 很高
磁盘持续读写
显存接近满
GPU-Util 经常 90%~100%
GPU 偶尔短暂掉到低利用率后重新升高
```

不要只看 Windows 任务管理器默认的 3D GPU 图。

建议：

```powershell
nvidia-smi -l 1
```

如果能看到 TransVLM Python 进程、显存持续占用、GPU-Util 持续变化，通常说明仍在运行。

查看 Python CPU / RAM：

```powershell
Get-Process python |
Sort-Object CPU -Descending |
Select-Object Id,CPU,@{Name='RAM_GB';Expression={[math]::Round($_.WorkingSet64 / 1GB, 2)}},StartTime
```

---

# 18. 拉片进度说明

当前 Shot V5 会显示 TransVLM 子阶段：

```text
准备 25fps 输入
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

whole-video NeuFlow 官方实现本身没有非常细的 batch 进度，因此这一阶段可能持续较久。

只要 GPU / CPU / RAM / Disk 仍然有明显活动，就不要仅因为百分比短时间不动而强制结束。

---

# 19. 日常启动

电脑重启以后一般只需要启动前后端，不需要重新安装依赖。

后端：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\python.exe -m uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
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

不需要每天重复运行：

```text
npm install
uv pip install
setup_transvlm_runtime.ps1
```

只有依赖或 Runtime 要求发生变化时才重装。

---

# 20. 更新项目

停止前后端后：

```powershell
cd D:\ai-drama-studio
git pull
```

如果 `engine\requirements.txt` 更新：

```powershell
cd D:\ai-drama-studio
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

如果前端依赖更新：

```powershell
cd D:\ai-drama-studio\frontend
npm install
```

如果 TransVLM Runtime / setup 脚本更新：

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

---

# 21. 拉片测试

不要求激活 `.venv`，直接使用主环境 Python：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\python.exe -m pytest engine/tests/v2/test_transvlm_shot_v5.py -q
.\.venv\Scripts\python.exe -m pytest engine/tests/v2/test_shot_v4_runtime_wiring.py -q
.\.venv\Scripts\python.exe -m pytest engine/tests/v2/test_shot_boundary_v4.py -q
```

当前 V2 全量：

```powershell
.\.venv\Scripts\python.exe -m pytest engine/tests/v2 -q
```

---

# 22. 本地数据目录

默认：

```text
D:\ai-drama-studio\data_v2\
```

主要包含：

```text
data_v2\
├─ studio_v2.sqlite3
├─ models\
└─ workspace\
```

如果要放到其他 SSD：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

然后在同一个 PowerShell 窗口启动后端。

---

# 23. 常见问题：命令无法识别

典型错误：

```text
无法将“xxx”项识别为 cmdlet、函数、脚本文件或可运行程序的名称
```

按顺序检查：

```text
1. 软件是否真的安装完成
2. 安装完成后是否关闭并重新打开 PowerShell
3. where.exe xxx 是否能找到程序
4. Windows PATH 是否包含正确安装目录
```

例如：

```powershell
where.exe git
where.exe node
where.exe uv
where.exe ffmpeg
```

---

# 24. 常见问题：uv 不存在

优先：

```powershell
winget install --id astral-sh.uv -e --source winget
```

如果 `msstore` 报证书错误，不要去掉 `--source winget`。

没有 winget：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

然后关闭 PowerShell、重新打开，再验证：

```powershell
uv --version
```

## 24.1 常见问题：No module named pip

如果执行：

```powershell
python -m pip ...
```

出现：

```text
No module named pip
```

说明这个 `uv venv` 没有 seed 传统 pip，不代表环境坏了。

直接改用：

```powershell
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
```

项目默认安装流程不要求 `.venv` 内存在 pip。

---

# 25. 常见问题：cuDNN 显示 91002

典型错误：

```text
TransVLM requires cuDNN >= 9.16; detected 91002
```

说明 PyTorch Windows wheel 实际加载了 cuDNN 9.10.2。

当前 setup 脚本会在隔离 TransVLM Runtime 中：

```text
安装 cuDNN 9.16
↓
stage 9.16 DLL 到 torch\lib
↓
重新验证 torch.backends.cudnn.version()
↓
执行 CUDA Conv3d 自检
```

处理：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

不要手工修改系统 CUDA / cuDNN。

---

# 26. 常见问题：Could not load libtorchcodec

典型错误：

```text
RuntimeError: Could not load libtorchcodec
```

Windows 下 TorchCodec 需要 Shared FFmpeg DLL，例如：

```text
avcodec-*.dll
avformat-*.dll
avutil-*.dll
```

当前 setup 会自动：

```text
扫描本机 Shared FFmpeg
↓
找不到时准备项目本地 pinned Shared FFmpeg
↓
记录 .runtime\TransVLM\ffmpeg_shared_bin.txt
↓
实际 import VideoDecoder 验证
```

处理：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

安装完成后彻底重启后端。

---

# 27. 常见问题：WinGet 说 FFmpeg 已安装但无法升级

如果看到：

```text
找到已安装的现有包。正在尝试升级已安装的包...
找不到可用的升级。
```

不要把它理解为 FFmpeg 安装失败。

当前项目不再依赖 WinGet 的升级返回码决定 TransVLM 是否可运行。

重新拉取最新脚本：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

setup 会自己找到或准备兼容 Shared FFmpeg。

---

# 28. 常见问题：拉片很慢 / RAM 和磁盘很高

这是 TransVLM whole-video NeuFlow 的典型特征。

用下面命令判断是否真在计算：

```powershell
nvidia-smi -l 1
```

如果 TransVLM `python.exe` 持续占显存，GPU-Util 经常上升，通常说明任务仍在正常工作。

---

# 29. 常见问题：端口被占用

后端：

```powershell
netstat -ano | findstr :8000
```

前端：

```powershell
netstat -ano | findstr :5173
```

---

# 30. 常见问题：PowerShell 禁止 .ps1

当前窗口临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

或者直接：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

不需要永久修改系统执行策略。

---

# 31. 全新电脑最短安装清单

## A. GUI

```text
1. 安装 NVIDIA 正式驱动
2. 安装/更新 Microsoft App Installer
3. 安装 Microsoft Visual C++ 2015-2022 x64 Redistributable
4. 重启电脑
```

## B. 新开 PowerShell

```powershell
winget --version
nvidia-smi

winget install --id Git.Git -e --source winget
winget install --id OpenJS.NodeJS.LTS -e --source winget
winget install --id astral-sh.uv -e --source winget
winget install --id Gyan.FFmpeg.Shared -e --source winget
```

## C. 关闭 PowerShell，再开新的 PowerShell

```powershell
git --version
node --version
npm --version
uv --version
ffmpeg -version
ffprobe -version
nvidia-smi
```

## D. 克隆项目

```powershell
cd D:\
git clone https://github.com/zdingwl/ai-drama-studio.git
cd D:\ai-drama-studio
```

## E. Python / 后端

```powershell
uv python install 3.12
uv venv .venv --python 3.12
uv pip install --python .\.venv\Scripts\python.exe -r .\engine\requirements.txt
.\.venv\Scripts\python.exe -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

## F. 前端

```powershell
cd D:\ai-drama-studio\frontend
npm install
npm run typecheck
```

## G. TransVLM

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

必须最终看到：

```text
[TransVLM] READY
```

## H. 启动后端

PowerShell A：

```powershell
cd D:\ai-drama-studio
.\.venv\Scripts\python.exe -m uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

## I. 启动前端

PowerShell B：

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

---

# 32. 安装完成验收清单

```text
[ ] Windows 10 / 11 64-bit
[ ] NVIDIA Driver 正常
[ ] nvidia-smi 正常
[ ] winget 正常
[ ] Git 正常
[ ] Node.js 正常
[ ] npm 正常
[ ] uv 正常
[ ] ffmpeg 正常
[ ] ffprobe 正常
[ ] 项目已经克隆
[ ] uv Python 3.12 正常
[ ] 主 .venv 正常
[ ] backend imports OK
[ ] npm install 完成
[ ] TransVLM setup 输出 READY
[ ] CUDA = True
[ ] cuDNN >= 91600
[ ] torchcodec=OK
[ ] runtime_status ready=true
[ ] FastAPI :8000 正常
[ ] Vite :5173 正常
[ ] 浏览器可以打开项目
[ ] 单集真实视频可以完成 TransVLM 拉片
```

任何一项不满足，先修对应环境，不要跳着继续。

---

# 33. 当前运行架构

主工程和 TransVLM 保持隔离：

```text
AI Drama Studio
│
├─ .venv
│  ├─ Python 3.12
│  ├─ FastAPI
│  ├─ SQLAlchemy / SQLite
│  └─ Shot / Revision / API
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

不要为了“统一环境”把 TransVLM 的 torch / cuDNN 直接装进主 `.venv`。

当前正式拉片链路：

```text
Source Video
→ TransVLM Transition Segments
→ Source PTS frame resolution
→ Shot Boundaries
→ frame-exact Reference Clip
→ Current Shot Revision
```

`TransNetV2 / PySceneDetect` 不再是当前正式自动拉片入口。
