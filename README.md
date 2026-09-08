# AI Drama Studio V3

AI 短剧生产工作台，当前处于 V3 从零重建阶段。

正式规划：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/03_Seko3.0_Skill架构逆向分析.md`
3. `docs/01_V3开发阶段与验收清单.md`
4. `docs/02_V3当前开发状态.md`
5. `AGENTS.md`

## 当前阶段

```text
P0 仓库重建基线            ✅ 完成
P1 新工程骨架              ✅ 完成
Seko Skill 架构研究        ✅ 第一版完成
P2 Project + Skill Kernel  ✅ 完成
P3 SourceAsset + 输入系统  ✅ 完成
P4 Task / ProviderJob      ▶ 当前阶段
```

V3 当前正式架构：

```text
Project Type
→ Root Project Skill
→ Agent / Plan Compiler
→ ProjectExecutionPlan
→ Professional Skills
→ Provider / Tools
→ Typed Artifacts
→ Artifact Graph
```

六种项目类型是真实后端枚举。每种项目绑定自己的 Root Skill，由 Skill 声明输入、专业能力、正式输出和完成标准，再编译成持久化执行计划。

第一版不会为了模仿 Seko 先开发复杂无限画布；后端先把正式 Artifact Graph 做正确，未来画布只是它的可视化。

## 六种项目

```text
REPLICA              复刻
REDRAW               重绘
TRANSLATION          翻译
NOVEL_TO_DRAMA       小说生成短剧
SCRIPT_TO_DRAMA      剧本生成短剧
SCRIPT_LOCALIZATION  剧本本土化
```

## 当前已可用的真实输入

视频类项目：

```text
多视频上传
→ Episode
→ ffprobe / decode preflight
→ 拖动排序
→ SOURCE_VIDEO Artifact revision
```

文本类项目：

```text
TXT / Markdown
→ SourceDocument revision
→ SOURCE_TEXT Artifact revision
```

原始 SourceAsset 不可变；同内容上传幂等。素材变化会使旧 Source Artifact / 依赖下游 STALE，并使当前执行计划失效，必须显式重新编译。

## 后端启动

要求 Python 3.12+，视频输入需要 FFmpeg / ffprobe 可执行文件。

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e "backend[dev]"
cd backend
uvicorn app.main:app --reload
```

健康检查：

```text
GET http://127.0.0.1:8000/api/v3/health
```

默认运行目录：

```text
backend/data/       SQLite
backend/artifacts/  Artifact 根目录
```

可以复制 `backend/.env.example` 为 `backend/.env` 修改配置。所有业务时间戳统一使用 UTC 存储；用户时区只在展示层转换。

## 前端启动

要求 Node.js 22+。

```bash
cd frontend
npm install
npm run dev
```

开发环境默认请求 `/api/v3`，Vite 会把 `/api/*` 代理到：

```text
http://127.0.0.1:8000
```

因此本地开发时应同时启动 FastAPI 和 Vite，不需要额外配置 CORS。

如后端不是运行在默认地址，可以在 `frontend/.env` 设置：

```text
VITE_API_PROXY_TARGET=http://127.0.0.1:9000
```

`VITE_API_BASE_URL` 只用于确实需要覆盖浏览器实际 API 根地址的部署场景；普通本地开发优先使用 Vite 代理。

## 验证

后端：

```bash
cd backend
python -m compileall app
python -c "from app.main import app; print(app.title)"
alembic upgrade head
pytest
```

前端：

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

P3 已通过包含真实 FFmpeg 视频生成 / ffprobe / decode 的 GitHub Actions V3 CI。当前状态和下一步以 `docs/02_V3当前开发状态.md` 为准。
