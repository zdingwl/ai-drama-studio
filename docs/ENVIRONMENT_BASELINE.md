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

## 12. Stable Gate

- [ ] Python/Node 依赖已锁定
- [ ] Native tool 要求已记录
- [ ] 新增模型来源/版本已记录
- [ ] 环境诊断可验证
- [ ] 未使用未约束的 `latest`
- [ ] 依赖升级经过相关回归测试
- [ ] Secrets 未进入 Git

---

## 13. F01 当前已验证依赖快照

截至 2026-08-23，`init_database()` 首次引入并实际测试：

```text
SQLAlchemy==2.0.50
alembic==1.18.4
pytest==9.0.2
```

声明文件：

```text
engine/requirements.txt
```

当前执行测试的容器：

```text
Python 3.13.5
```

注意：项目正式目标基线仍是 Python 3.11。当前 6 个数据库测试 PASS 只能证明上述依赖和代码在测试容器可运行，**不能视为 Python 3.11 Stable Gate 已完成**。F01 进入 `READY_FOR_REVIEW` 前必须在目标 Python 3.11 环境重新安装声明依赖并运行完整 F01 测试。

本次依赖不涉及 CUDA、PyTorch、FFmpeg 或 GPU，不改变 RTX 4060 Ti 16GB 的运行约束。
