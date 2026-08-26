# AI Drama Studio — Windows 裸机安装与运行手册

> 适用项目：`zdingwl/ai-drama-studio`
>
> 当前拉片基线：Reference Video V2 / Shot V5 / TransVLM-first。
>
> **本手册按“刚装好的 Windows，除了浏览器和系统自带 Windows PowerShell，其他开发工具都没有”来写。**
>
> 如果你的电脑上执行 `git`、`python`、`node`、`npm`、`uv`、`ffmpeg` 都提示“无法识别”，这是本手册的正常起点，不需要先自己猜着装环境。

---

# 0. 先看这里：一台什么都没有的 Windows 应该从哪开始

第一次安装时，不要先执行项目命令。

正确顺序是：

```text
浏览器 / Windows 自带 PowerShell
↓
安装 NVIDIA 驱动
↓
安装 Microsoft App Installer（获得 winget）
↓
用 winget 安装 Git / Node.js / uv / FFmpeg Shared
↓
重新打开 PowerShell
↓
克隆 AI Drama Studio
↓
用 uv 安装 Python 3.12 和主工程 .venv
↓
安装后端依赖
↓
安装前端依赖
↓
运行 setup_transvlm_runtime.ps1
↓
启动后端
↓
启动前端
↓
浏览器打开项目
```

如果其中某一步提示“命令不存在”，不要继续往下执行，先按该步骤的“命令不存在怎么办”处理。

---

# 1. 最低硬件 / 系统要求

## 1.1 Windows

推荐：

```text
Windows 10 64-bit
或
Windows 11 64-bit
```

系统自带的 **Windows PowerShell 5.1** 就可以完成安装。

打开方式：

```text
开始菜单
→ 搜索 PowerShell
→ 打开 Windows PowerShell
```

安装软件时如果权限不足，可以：

```text
右键 Windows PowerShell
→ 以管理员身份运行
```

## 1.2 NVIDIA GPU

当前 TransVLM 拉片要求 NVIDIA GPU。

建议至少：

```text
8 GB 显存
```

RTX 3060 Ti 8GB 可以运行，但 TransVLM 会非常吃显存、内存和磁盘。

如果机器没有 NVIDIA GPU，当前正式 TransVLM 拉片流程不适合直接运行。

## 1.3 内存

建议：

```text
最低：32 GB
推荐：64 GB
```

原因是 TransVLM 官方 whole-video NeuFlow 会一次性处理整段视频，长视频可能占用大量系统内存。

## 1.4 磁盘

建议至少预留：

```text
50 GB 可用空间
```

模型、Python Runtime、Torch、临时视频、Optical Flow、Reference Clip 都会占磁盘。

推荐项目和 `data_v2` 放 SSD / NVMe，不建议放机械硬盘。

---

# 2. 第一步：安装 NVIDIA 驱动

如果是新装 Windows，先装显卡驱动。

打开浏览器进入 NVIDIA 官方驱动下载页：

```text
https://www.nvidia.com/Download/index.aspx
```

按你的显卡型号安装最新正式驱动。

安装完成后建议重启电脑。

重启以后，打开 PowerShell：

```powershell
nvidia-smi
```

正常应该看到类似：

```text
NVIDIA-SMI ...
Driver Version: ...
CUDA Version: ...
GPU Name: NVIDIA GeForce RTX ...
```

如果提示：

```text
无法将“nvidia-smi”项识别为 cmdlet...
```

说明 NVIDIA 驱动还没有正确安装，不要继续安装 TransVLM。

> 不需要另外手工安装系统 CUDA Toolkit。项目使用 PyTorch 自带 CUDA Runtime。

---

# 3. 第二步：让 Windows 具备 winget

后续最省事的安装方式是 `winget`。

先打开 PowerShell：

```powershell
winget --version
```

## 3.1 如果 winget 已经存在

看到类似：

```text
v1.x.x
```

直接进入下一章。

## 3.2 如果 winget 提示“无法识别”

不要继续输入 Git / Python 等命令。

打开：

```text
Microsoft Store
```

搜索：

```text
App Installer
```

发布者应为：

```text
Microsoft Corporation
```

安装或更新 **App Installer（应用安装程序）**。

安装完成后：

```text
关闭所有 PowerShell 窗口
→ 重新打开 PowerShell
```

再次执行：

```powershell
winget --version
```

只有这个命令成功后再继续。

## 3.3 Microsoft Store 不能用怎么办

可以先通过浏览器去 Microsoft 的 App Installer / winget 官方说明安装：

```text
https://learn.microsoft.com/windows/package-manager/winget/
```

如果这台 Windows 被企业策略禁用了 Store/winget，也可以走本手册后面的“完全不用 winget 的手工安装方式”。

---

# 4. 第三步：一次性安装基础工具

确认：

```powershell
winget --version
```

正常后，在 PowerShell 依次执行。

## 4.1 Git

```powershell
winget install --id Git.Git -e
```

## 4.2 Node.js

```powershell
winget install --id OpenJS.NodeJS.LTS -e
```

项目使用 Vite 8，Node.js 需要满足：

```text
Node 20.19+
或
Node 22.12+
```

使用当前 Node.js LTS 即可。

## 4.3 uv

```powershell
winget install --id astral-sh.uv -e
```

`uv` 后面负责：

```text
安装 Python 3.12
创建主工程 .venv
创建 TransVLM 独立 Python 3.12 Runtime
安装 Python 依赖
```

所以新机器不需要先单独安装 Python。

## 4.4 FFmpeg Shared

TransVLM 使用 TorchCodec，Windows 下必须能找到 FFmpeg Shared DLL。

安装：

```powershell
winget install --id Gyan.FFmpeg.Shared -e
```

项目的 TransVLM 安装脚本会进一步检查 shared build，并在需要时处理兼容版本。

## 4.5 Microsoft Visual C++ Runtime

PyTorch / TorchCodec 等 Windows 原生 DLL 依赖 Microsoft Visual C++ Runtime。

可以使用微软官方安装程序：

```text
https://aka.ms/vs/17/release/vc_redist.x64.exe
```

下载后双击安装。

---

# 5. 安装基础工具后，必须重新打开 PowerShell

这是 Windows 新手最容易漏的一步。

安装完 Git / Node / uv / FFmpeg 后：

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

这 7 个命令都应该能正常执行。

如果某个命令提示“无法识别”，先不要继续。

可以定位程序：

```powershell
where.exe git
where.exe node
where.exe npm
where.exe uv
where.exe ffmpeg
where.exe ffprobe
where.exe nvidia-smi
```

## 5.1 典型正确结果

类似：

```text
git version 2.x
v22.x.x
10.x.x
uv 0.x.x
ffmpeg version 8.x
...
NVIDIA-SMI ...
```

具体小版本不要求完全一样。

---

# 6. 如果完全不想用 winget：浏览器手工安装方式

如果 `winget` 无法使用，可以用浏览器下载安装。

## 6.1 Git

浏览器：

```text
https://git-scm.com/download/win
```

下载 64-bit Git for Windows 安装包。

安装时保持默认选项即可，重点保证 Git 会加入 PATH。

## 6.2 Node.js

浏览器：

```text
https://nodejs.org/en/download
```

下载 Windows x64 的 LTS 安装包，正常下一步安装。

## 6.3 uv

浏览器：

```text
https://docs.astral.sh/uv/getting-started/installation/
```

如果 PowerShell 本身可以联网，也可以用官方 PowerShell 安装命令：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完成后一定要重新打开 PowerShell。

## 6.4 FFmpeg Shared

浏览器：

```text
https://www.gyan.dev/ffmpeg/builds/
```

需要的是 **full shared build**，不是只有 `ffmpeg.exe` 的 static build。

正确的 `bin` 目录除了：

```text
ffmpeg.exe
ffprobe.exe
```

还应该包含类似：

```text
avcodec-*.dll
avformat-*.dll
avutil-*.dll
```

只有这样 TorchCodec 才能正常加载。

## 6.5 NVIDIA Driver

浏览器：

```text
https://www.nvidia.com/Download/index.aspx
```

安装对应显卡驱动。

---

# 7. 获取 AI Drama Studio 项目

基础工具都验证成功以后，再获取项目。

推荐目录：

```text
D:\ai-drama-studio
```

如果你的电脑没有 D 盘，可以改成：

```text
C:\ai-drama-studio
```

## 7.1 使用 Git 克隆

例如使用 D 盘：

```powershell
cd D:\
git clone https://github.com/zdingwl/ai-drama-studio.git
cd D:\ai-drama-studio
```

验证：

```powershell
git status
```

正常会显示当前分支和工作区状态。

## 7.2 如果 Git 还是不能用：浏览器下载 ZIP

浏览器打开项目主页：

```text
https://github.com/zdingwl/ai-drama-studio
```

点击：

```text
Code
→ Download ZIP
```

解压后把目录改名为：

```text
ai-drama-studio
```

放到：

```text
D:\ai-drama-studio
```

这种方式可以先安装运行，但以后更新项目仍推荐安装 Git。

---

# 8. 用 uv 安装 Python 3.12

进入项目：

```powershell
cd D:\ai-drama-studio
```

如果你使用 C 盘，就改成自己的路径。

执行：

```powershell
uv python install 3.12
```

验证：

```powershell
uv python list
```

应该能看到 Python 3.12。

> 新机器推荐让 uv 管理 Python，不要求系统已经存在 `python.exe`。

---

# 9. 创建主工程 .venv

在项目根目录：

```powershell
cd D:\ai-drama-studio
uv venv .venv --python 3.12
```

创建成功后：

```text
D:\ai-drama-studio\.venv\
```

应该存在。

激活：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

验证：

```powershell
python --version
```

应该是：

```text
Python 3.12.x
```

## 9.1 PowerShell 提示禁止运行脚本

执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

这个设置只影响当前 PowerShell 窗口，不会永久修改整台机器策略。

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

---

# 10. 安装主工程后端依赖

确认命令行前面已经出现：

```text
(.venv)
```

然后：

```powershell
python -m pip install --upgrade pip
pip install -r engine\requirements.txt
```

安装完成后验证：

```powershell
python -c "import fastapi, sqlalchemy, cv2; print('backend imports OK')"
```

应该输出：

```text
backend imports OK
```

> 主工程 `.venv` 和 TransVLM `.runtime\TransVLM\inference\.venv` 是两个独立 Runtime，不要混装。

---

# 11. 安装前端依赖

打开一个新的 PowerShell，执行：

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

如果提示：

```text
npm 无法识别
```

说明 Node.js 没有安装好或 PowerShell 没重新打开。

执行：

```powershell
node --version
npm --version
```

先把 Node 环境处理好。

---

# 12. 安装 TransVLM Runtime

这是拉片最重要的一步。

先关闭正在运行的后端。

进入项目根目录：

```powershell
cd D:\ai-drama-studio
```

## 12.1 安装前完整检查

执行：

```powershell
Get-Command git,uv,ffmpeg,nvidia-smi
```

这四个必须全部找到。

也建议执行：

```powershell
git --version
uv --version
ffmpeg -version
nvidia-smi
```

## 12.2 执行 TransVLM 自动安装脚本

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

脚本会自动完成：

```text
1. 检查 git / uv / ffmpeg / nvidia-smi
2. 克隆或更新 HeyGen 官方 TransVLM
3. 读取 NVIDIA Driver
4. 选择兼容的 PyTorch CUDA group
5. 用 uv 安装 Python 3.12
6. 创建 TransVLM 独立 .venv
7. 安装官方 inference 依赖
8. 安装 / 校验 cuDNN 9.16
9. Windows 下把正确 cuDNN DLL 注入隔离 torch runtime
10. 检查 / 准备 FFmpeg Shared Runtime
11. 验证 TorchCodec VideoDecoder
12. 下载 TransVLM Qwen3-VL 4B checkpoint
13. 下载 NeuFlow v2 权重
14. 执行 infer_video.py --help 自检
```

第一次执行时间会很长，因为要下载多 GB 模型和 PyTorch Runtime。

## 12.3 正常成功标志

最后应该看到：

```text
[TransVLM] READY
```

并且包含类似：

```text
Python: ...\.runtime\TransVLM\inference\.venv\Scripts\python.exe
Checkpoint: ...\pretrained\TransVLM-v1
Backend: hf
CUDA group: cu128 / cu130
```

---

# 13. TransVLM 安装后必须做的检查

## 13.1 CUDA / cuDNN

```powershell
D:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe -c "import torch; print('cuda=',torch.cuda.is_available()); print('gpu=',torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'NO GPU'); print('torch=',torch.__version__); print('torch cuda=',torch.version.cuda); print('cudnn=',torch.backends.cudnn.version())"
```

正常至少应该满足：

```text
cuda= True
gpu= NVIDIA ...
cudnn= 91600 或更高
```

## 13.2 TorchCodec

```powershell
D:\ai-drama-studio\.runtime\TransVLM\inference\.venv\Scripts\python.exe -c "from torchcodec.decoders import VideoDecoder; print('torchcodec=OK')"
```

应该输出：

```text
torchcodec=OK
```

## 13.3 项目 Runtime 状态

先激活主 `.venv`：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

然后：

```powershell
python -c "from engine.app.transvlm_runtime_v5 import runtime_status; import json; print(json.dumps(runtime_status(), ensure_ascii=False, indent=2))"
```

正常应该有：

```json
{
  "ready": true,
  "profile": "TransVLM-Qwen3-VL-4B-Instruct",
  "backend": "hf",
  "device": "cuda:0",
  "missing": []
}
```

如果：

```text
ready = false
```

先看：

```text
missing
```

不要直接开始拉片。

---

# 14. 启动后端

打开 PowerShell A：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

正常会显示：

```text
Uvicorn running on http://127.0.0.1:8000
```

## 14.1 健康检查

另开 PowerShell：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

应该返回类似：

```text
status       : ok
architecture : reference-video-v2
app_version  : ...
```

如果 8000 端口被占用：

```powershell
netstat -ano | findstr :8000
```

找到占用进程后再处理。

---

# 15. 启动前端

打开 PowerShell B：

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

默认应该启动在：

```text
http://127.0.0.1:5173
```

Vite 会把 `/api` 自动代理到：

```text
http://127.0.0.1:8000
```

浏览器打开：

```text
http://127.0.0.1:5173
```

---

# 16. 第一次业务验收：只测一集视频

第一次不要一次导入很多集，也不要先做资产提取。

正确验收顺序：

```text
1. 新建项目
2. 导入 1 个短视频
3. 点击单集拉片
4. 等待 TransVLM 完成
5. 看 Shot 数量
6. 检查明显 Hard Cut 是否漏切
7. 检查是否产生大量碎片 Shot
8. 检查相邻 Shot 的 OUT / NEXT IN
9. 确认拉片结果可用
10. 再批量处理其他剧集
```

拉片正式链路：

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

# 17. TransVLM 运行时为什么看起来很重

运行期间出现下面这些现象是正常的：

```text
内存占用很高
磁盘持续读写
GPU 显存接近满
GPU 利用率经常 90%~100%
某些阶段 GPU 利用率突然降低后又升高
```

例如 RTX 3060 Ti 8GB 在 TransVLM 推理时显存接近：

```text
7.7 ~ 7.9 GB / 8 GB
```

是可能出现的。

查看 GPU：

```powershell
nvidia-smi -l 1
```

如果能看到 TransVLM Python 进程，并且：

```text
GPU-Util 持续变化
显存被占用
```

通常说明模型仍在正常工作。

停止监控：

```text
Ctrl + C
```

---

# 18. 拉片进度阶段说明

当前 V5 会尽量显示 TransVLM 子阶段：

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

其中 whole-video NeuFlow 官方实现本身没有细粒度 batch 进度，所以这一阶段可能持续较久。

只要：

```text
GPU / CPU / RAM / Disk 仍然有活动
```

就不要仅因为百分比短时间不动就强制结束任务。

---

# 19. 日常启动，不需要重新安装

电脑重启以后，平时只需要两个 PowerShell。

## 19.1 后端

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
```

## 19.2 前端

```powershell
cd D:\ai-drama-studio\frontend
npm run dev
```

浏览器：

```text
http://127.0.0.1:5173
```

不需要每次重跑：

```text
npm install
pip install
setup_transvlm_runtime.ps1
```

只有依赖发生变化时才重装。

---

# 20. 更新项目

先停止前端和后端：

```text
Ctrl + C
```

然后：

```powershell
cd D:\ai-drama-studio
git pull
```

查看最新提交：

```powershell
git log -5 --oneline
```

如果后端依赖更新：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r engine\requirements.txt
```

如果前端依赖更新：

```powershell
cd D:\ai-drama-studio\frontend
npm install
```

如果 TransVLM Runtime 要求更新：

```powershell
cd D:\ai-drama-studio
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

---

# 21. 拉片测试

激活主 `.venv`：

```powershell
cd D:\ai-drama-studio
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

TransVLM V5：

```powershell
python -m pytest engine/tests/v2/test_transvlm_shot_v5.py -q
```

正式入口：

```powershell
python -m pytest engine/tests/v2/test_shot_v4_runtime_wiring.py -q
```

Reference Clip 帧所有权：

```powershell
python -m pytest engine/tests/v2/test_shot_boundary_v4.py -q
```

当前 V2 全量测试：

```powershell
python -m pytest engine/tests/v2 -q
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

其中：

```text
workspace
```

会存放导入视频、预处理文件、Shot Run、Reference Clip 等数据。

可以把业务数据放到其他 SSD：

```powershell
$env:AI_DRAMA_STUDIO_HOME="E:\ai-drama-studio-data"
```

然后再启动后端。

注意：只在当前 PowerShell 设置 `$env:`，关闭窗口后就失效。

---

# 23. 常见问题：git / node / npm / uv / ffmpeg 都无法识别

如果看到：

```text
无法将“xxx”项识别为 cmdlet、函数、脚本文件或可运行程序的名称
```

按顺序排查：

```text
1. 软件是否真的安装完成
2. 安装以后是否关闭并重新打开 PowerShell
3. where.exe xxx 能否找到
4. Windows PATH 是否包含安装目录
```

例如：

```powershell
where.exe git
where.exe node
where.exe uv
where.exe ffmpeg
```

如果 `where.exe` 完全找不到，说明不是项目问题，是该基础软件还没有正确安装。

---

# 24. 常见问题：uv 不存在

优先：

```powershell
winget install --id astral-sh.uv -e
```

没有 winget：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

然后：

```text
关闭 PowerShell
重新打开
```

验证：

```powershell
uv --version
```

---

# 25. 常见问题：cuDNN 显示 91002

如果 TransVLM 安装报：

```text
TransVLM requires cuDNN >= 9.16; detected 91002
```

说明 PyTorch Windows wheel 实际加载了 cuDNN 9.10.2。

当前项目安装脚本已经会在隔离 TransVLM Runtime 中：

```text
安装 cuDNN 9.16
↓
把 9.16 DLL stage 到该 Runtime 的 torch\lib
↓
重新验证 torch.backends.cudnn.version()
↓
执行 CUDA Conv3d 自检
```

处理方式：

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

并显示：

```text
libtorchcodec_core8.dll
libtorchcodec_core7.dll
...
```

最常见原因是 Windows 上只有 FFmpeg static build，没有：

```text
avcodec-*.dll
avformat-*.dll
avutil-*.dll
```

当前项目脚本会自动检查 Shared FFmpeg Runtime，并记录：

```text
.runtime\TransVLM\ffmpeg_shared_bin.txt
```

处理：

```powershell
cd D:\ai-drama-studio
git pull
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

安装完成后彻底重启后端。

---

# 27. 常见问题：拉片很慢 / 内存和硬盘占用很高

TransVLM whole-video NeuFlow 本身就是重任务。

不要仅凭 Windows 任务管理器的默认 GPU 图判断。

用：

```powershell
nvidia-smi -l 1
```

如果看到：

```text
python.exe
GPU-Util 接近 100%
显存持续占用
```

通常说明 GPU 正在正常工作。

查看 Python CPU / 内存：

```powershell
Get-Process python |
Sort-Object CPU -Descending |
Select-Object Id,CPU,@{Name='RAM_GB';Expression={[math]::Round($_.WorkingSet64 / 1GB, 2)}},StartTime
```

---

# 28. 常见问题：端口被占用

后端 8000：

```powershell
netstat -ano | findstr :8000
```

前端 5173：

```powershell
netstat -ano | findstr :5173
```

如需查看 PID：

```powershell
tasklist | findstr <PID>
```

---

# 29. 常见问题：PowerShell 执行策略阻止 .ps1

当前窗口临时放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

然后：

```powershell
.\.venv\Scripts\Activate.ps1
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_transvlm_runtime.ps1
```

不需要永久修改系统执行策略。

---

# 30. 一台全新电脑的最短安装清单

如果你只想照着做，不想理解细节，按下面顺序执行。

## A. 浏览器 / GUI

```text
1. 安装 NVIDIA 驱动
2. Microsoft Store 安装/更新 App Installer
3. 安装 Microsoft Visual C++ 2015-2022 x64 Redistributable
4. 重启电脑
```

## B. 新开 PowerShell

确认：

```powershell
winget --version
nvidia-smi
```

然后：

```powershell
winget install --id Git.Git -e
winget install --id OpenJS.NodeJS.LTS -e
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg.Shared -e
```

## C. 关闭 PowerShell，再开一个新的 PowerShell

验证：

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
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r engine\requirements.txt
```

## F. 前端

```powershell
cd D:\ai-drama-studio\frontend
npm install
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
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
uvicorn engine.app.main:app --reload --host 127.0.0.1 --port 8000
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

# 31. 安装完成验收清单

全部满足才算环境安装完成：

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
[ ] 单集真实视频可以进入 TransVLM 拉片
```

任何一项不满足，都先修对应环境，不要跳着继续。

---

# 32. 当前运行架构说明

主工程和 TransVLM 必须保持隔离：

```text
AI Drama Studio
│
├─ .venv
│  ├─ FastAPI
│  ├─ SQLAlchemy / SQLite
│  ├─ FFmpeg 调度
│  └─ Shot / Revision / Asset API
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
