# Windows 统一启动器进程生命周期与退出清理整改

> 日期：2026-09-13  
> 状态：统一启动器生命周期整改。本文优先级高于 `docs/37` 中“复用已有服务 / Ctrl+C 才回收”的旧生命周期描述。  
> 本整改只处理本地运行进程生命周期，不改变 P14 Artifact、ProviderJob、Timing 或阶段能力状态。

## 1. 问题

旧版 `start.cmd -> start_studio_guard.py -> start_studio.py` 主要依赖 Python `finally` 调用 `taskkill /T` 回收本次创建的子进程。

这只覆盖 Python 能正常收到 `KeyboardInterrupt` / 正常异常退出的情况。Windows 用户直接关闭 CMD / PowerShell 窗口、终止 launcher Python，或 launcher 被异常结束时，Python `finally` 可能没有机会执行；而 backend、Vite、IndexTTS 又使用独立子进程组，因此可能成为孤儿继续占用：

```text
5173  Vite
8000  FastAPI / Uvicorn reload tree
8092  IndexTTS-2.5 native adapter
```

结果是 `start.cmd` 已经退出，但任务管理器或端口仍然存在 Studio 进程。

## 2. Windows 正式生命周期

Windows 统一启动器现在在启动任何服务之前：

1. 为当前 checkout 获取单实例 named mutex；
2. 创建 Windows Job Object；
3. 设置 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`；
4. 把 launcher Python 自身加入该 Job；
5. 再启动 IndexTTS、FastAPI、Vite。

子进程继承 Job membership，因此正式结构变为：

```text
start.cmd
  -> start_studio_guard.py
     -> start_studio.py [Windows Job owner]
        ├─ IndexTTS PowerShell / Python tree
        ├─ Uvicorn reload / worker tree
        └─ npm / Vite / Node tree
```

当 `start_studio.py` 退出时，不论是 Ctrl+C、正常退出、异常崩溃还是直接关闭控制台窗口，Windows 都会关闭 launcher 持有的 Job handle；`KILL_ON_JOB_CLOSE` 由操作系统终止仍留在 Job 内的全部进程。Python `finally` 的显式 `taskkill` 仍保留作为正常退出时的第一层清理，但不再是唯一保障。

如果 Windows 无法把 launcher 放进该 Job，启动器 fail closed，不能在“无法保证退出回收”的状态下继续启动服务。

## 3. 单实例

同一个仓库 checkout 同一时刻只允许一个统一 launcher。

再次运行 `start.cmd` 时，如果该 checkout 的 launcher mutex 仍存在，新启动器直接提示已有实例，不会启动第二套 5173 / 8000 / 8092，也不会抢占第一套运行中的服务。

## 4. 旧孤儿进程迁移

本整改上线前已经遗留的旧进程不属于新 Job，无法由 Job Object 追溯接管。

因此新 launcher 第一次运行时会检查 5173 / 8000 / 8092：

- listener 的 executable / command line 明确属于当前仓库 checkout：视为旧统一启动器遗留进程，安全回收后重新启动并纳入新 Job；
- 8000 backend 有一个额外的强身份规则：如果 `/api/v3/health` 返回的 `runtime_fingerprint` 与当前 checkout 按相同源码哈希规则计算的 fingerprint 完全一致，则即使该 backend 由仓库外的 uv-managed Python 可执行文件启动、命令行中没有仓库绝对路径，也确认属于当前 checkout 并允许安全回收；
- listener 无法识别、backend fingerprint 不匹配、或属于其他程序 / 其他 checkout：fail closed，不杀未知进程。

`runtime_fingerprint` 在 backend 启动时冻结，来自当前 `backend/app/**/*.py` 的路径感知 SHA256；因此一次 `git pull` 后，旧 backend 即使仍然健康，也不能伪装成当前源码实例。

Windows 新生命周期不再为了节省一次启动而复用当前 checkout 的旧后台服务，因为一旦复用，launcher 退出时就无法保证它们一起结束。

## 5. 显式 stop.cmd

仓库根目录新增：

```text
stop.cmd
```

用途：

1. 停止当前 checkout 正在运行的新 launcher；Job 随 launcher 关闭并终止完整子进程树；
2. 清理本整改以前遗留的当前 checkout 旧 5173 / 8000 / 8092 listener；
3. 遇到未知端口占用时只报错，不误杀。

推荐 Windows 操作：

```text
git pull
stop.cmd
start.cmd
```

第一次升级到本整改时先运行一次 `stop.cmd`，之后正常情况下只需要 `start.cmd`；关闭 launcher 窗口即可停止整套 Studio。

## 6. PID 诊断

运行期间 launcher PID 写入：

```text
.runtime/studio-launcher.pid
```

该文件只用于当前 checkout 的 stop / 诊断。`stop.cmd` 在按 PID 停止前必须再次核对该 PID 的 command line 确实属于当前仓库的 `scripts/start_studio.py`；PID 文件陈旧或 PID 已被其他程序复用时不得误杀。

`.runtime/` 继续是本地运行缓存，不进入 Git。

## 7. P14 状态

此整改不产生任何 P14 验收事实，也不自动修改 capability availability。P14 是否 PASS 仍由正式音频、Timing、技术验收与人工验收事实决定。
