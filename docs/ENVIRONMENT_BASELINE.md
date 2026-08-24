# AI Drama Studio — Environment Baseline

## 1. 目的

本项目会经历多次开发会话、模型切换、依赖升级和新电脑恢复。

必须保证：

> 未来的新 Agent / 新开发机可以知道“当时到底用了什么版本”，而不是依赖 `latest`、口头记忆或某台电脑的偶然环境。

---

## 2. 禁止依赖 latest

禁止在正式开发规则里写：

```text
安装最新 PyTorch
安装最新 CUDA
安装最新 FFmpeg
安装最新 Node
```

关键依赖必须有可复现版本或明确兼容范围。

---

## 3. 必须锁定/记录的环境

### Python

至少记录：

```text
Python exact version
package manager version
lock file
PyTorch version
CUDA runtime expectation
```

推荐：

```text
.python-version
pyproject.toml
uv.lock（或其它明确 lock）
```

如果不用 uv，也必须存在等价锁定机制。

### Frontend

至少记录：

```text
Node exact major/minor
package manager + version
package lock
```

推荐：

```text
.node-version / .nvmrc
package.json
pnpm-lock.yaml / package-lock.json
```

### Native Tools

记录：

```text
FFmpeg version/build
FFprobe version
NVIDIA driver
CUDA runtime/toolkit（如实际依赖）
```

不要仅写“已安装 FFmpeg”。

---

## 4. 本地模型基线

每个本地模型至少记录：

```text
logical model id
model name
source
repository/release/commit（能获取时）
weight filename
weight checksum/hash（能获取时）
license note
runtime dependency
expected VRAM
```

例如不要只写：

```text
Whisper large-v3
```

应能进一步确定具体实现和模型来源。

模型下载缓存不提交 Git，但 manifest 必须提交。

建议最终形成：

```text
config/models.yaml
```

Model Registry 的完整能力可以后续 Feature 增强，但从第一版开始禁止完全无版本记录。

---

## 5. Provider 模型版本

闭源 API 也必须尽量记录：

```text
provider
model id
model alias
API version
request schema version
first verified date
last verified date
```

如果 Provider 只提供会漂移的 alias：

- 记录 alias；
- 记录调用日期；
- 记录关键输出 metadata；
- 不假设同名 alias 永远行为一致。

---

## 6. 环境诊断

应用/开发脚本应最终支持输出一个环境诊断快照，例如：

```json
{
  "python": "3.11.x",
  "node": "xx.x.x",
  "pytorch": "x.x.x",
  "cuda_available": true,
  "gpu": "NVIDIA GeForce RTX 4060 Ti",
  "vram_mb": 16384,
  "ffmpeg": "...",
  "platform": "Windows ..."
}
```

诊断信息用于：

- Session Handoff；
- Bug 排查；
- 新电脑恢复；
- 真实素材测试记录。

不得在诊断里输出 API Key / Token。

---

## 7. 新增依赖规则

Feature 如果新增依赖，必须同步：

1. 更新依赖声明；
2. 更新 lock；
3. 更新 Feature 文档；
4. 记录为什么需要它；
5. 记录是否有替代方案；
6. 确认许可证/使用约束（适用时）；
7. 在 Session Handoff 记录。

缺少任何关键项时，不允许把“我本地装好了”当作完成。

---

## 8. 升级依赖规则

禁止为了开发某个 Feature 顺手做无关大升级。

依赖升级应满足：

```text
明确升级原因
→ 记录旧版本/新版本
→ 影响分析
→ 当前 Feature 测试
→ 受影响 Stable Feature 回归测试
→ 更新 lock / baseline
```

破坏兼容的升级必须单独记录 migration / remediation。

---

## 9. RTX 4060 Ti 16GB 基线

当前开发硬件基线：

```text
NVIDIA RTX 4060 Ti 16GB
```

开发阶段原则：

- 正确性优先；
- GPU concurrency 默认 1；
- 模型按需 load/run/unload；
- 不因速度慢而擅自引入大规模基础设施；
- 如果某 Feature 只能在 >16GB 显存运行，必须在 Contract 中明确，而不能开发到一半才发现。

---

## 10. 环境文件与 Secret 分离

可以提交：

```text
.env.example
config example
runtime baseline
model manifest
```

禁止提交：

```text
.env.local
真实 API Key
Provider Token
账号密码
私有证书
```

---

## 11. Feature Contract 必须回答

如果 Feature 新增技术依赖：

1. 新增什么依赖？
2. 为什么需要？
3. 精确版本/lock 如何记录？
4. 是否影响 CUDA / PyTorch / FFmpeg？
5. 是否改变 4060 Ti 16GB 可运行性？
6. 新电脑如何安装？
7. 如何验证安装成功？

---

## 12. F04 本地自动拉片实际基线（2026-08-24）

F04 是第一个正式引入 PyTorch 本地模型的 Feature。其实现基线固定如下：

```text
Feature: F04 自动拉片
Detector: TransNetV2
Python package: transnetv2-pytorch==1.0.5
PyTorch: torch==2.5.1
NumPy: numpy==2.1.3
Pandas: pandas==2.2.3
Pillow: pillow==11.1.0
Tqdm: tqdm==4.67.1
ffmpeg-python: 0.2.0
future: 1.0.0
```

完整 Python 依赖以：

```text
engine/requirements.txt
```

为准；模型分发身份、wheel SHA-256、权重文件名和算法 Profile 以：

```text
config/models.yaml
```

为准。

### 12.1 为什么选这个实现

F04 需要本地 Shot Boundary Detection。旧草案的 FFmpeg SCDet 只基于传统画面差分；用户在 F04 开发开始前明确选择效果优先的本地 TransNetV2 路线，因此 V1 正式实现使用 `transnetv2-pytorch==1.0.5`。

PySceneDetect 可以保留为未来对比/诊断工具，但不属于 F04 V1 正式结果生成链路。

### 12.2 模型权重

固定权重文件：

```text
transnetv2-pytorch-weights.pth
```

F04 不允许模型随机初始化。如果固定 Python 分发安装后找不到该权重文件，运行必须返回：

```text
SHOT_DETECTION_MODEL_UNAVAILABLE
```

而不是继续产生无意义 Shot。

Python 分发 wheel 固定：

```text
transnetv2_pytorch-1.0.5-py3-none-any.whl
SHA-256:
9f8e72085526aaa95383d219b6750b1fa45b865fd10d840cafa12ef78ab3bf27
```

### 12.3 设备策略

固定：

```text
preferred_device = auto
```

当前 Windows + NVIDIA 基线期望：

```text
CUDA 可用 → CUDA
CUDA 不可用 → CPU fallback
GPU concurrency = 1
```

CPU fallback 只影响速度，不允许改变 F04 时间契约。MPS 不是当前 Windows/NVIDIA 基线。

每次 ready Detection Run 必须保存：

```text
torch_version
detector_device
ffprobe_version
```

因此不能只看机器环境猜测“当时到底在哪个设备上跑的”。

### 12.4 FFmpeg / FFprobe 的职责

F04 的 TransNetV2 只判断 transition frame；正式时间仍由 FFprobe `-show_frames` 返回的真实 PTS 决定。

禁止：

```text
frame_index / fps
```

推算正式镜头时间。

FFmpeg / FFprobe 沿用 F03 已验证的本地原生工具安装。新电脑必须确保二者均在 PATH 中，并执行：

```text
ffmpeg -version
ffprobe -version
```

### 12.5 新电脑安装

项目 Python 业务基线继续保持：

```text
Python 3.11
```

安装：

```text
python -m pip install -r engine/requirements.txt
```

随后验证：

```text
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
python -c "import transnetv2_pytorch; import importlib.metadata as m; print(m.version('transnetv2-pytorch'))"
ffmpeg -version
ffprobe -version
```

注意：`torch==2.5.1` 的具体 CUDA wheel 获取方式取决于当前 Windows/CUDA 安装源。**不得为了让 `cuda_available` 变成 true 而擅自升级到其它 PyTorch 大版本。** 如需改 PyTorch/CUDA 组合，必须先按本文件第 8 节做依赖升级评审。

### 12.6 当前验收边界

2026-08-24 当前 ChatGPT 工具容器仅确认：

```text
FFmpeg/FFprobe 7.1.5 可用
```

该工具容器是 Python 3.13 + CPU 环境，且没有安装 `transnetv2-pytorch`，**不等于用户 Windows 项目运行环境**。

因此在 F04 用户验收前，必须在用户本机执行真实视频 smoke test，并记录：

```text
Python 实际 patch 版本
PyTorch 2.5.1
CUDA available
GPU 名称
TransNetV2 1.0.5
FFmpeg / FFprobe 实际版本
真实视频 Shot Count
应用重启后结果可读取
```

未完成本机 smoke test 之前，不允许声称“F04 已在 RTX 4060 Ti 上验证通过”。
