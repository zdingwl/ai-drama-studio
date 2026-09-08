# AI Drama Studio V3

AI 短剧生产工作台，当前处于 V3 从零重建阶段。

正式规划：

1. `docs/00_V3产品与系统详细规划.md`
2. `docs/01_V3开发阶段与验收清单.md`
3. `AGENTS.md`

## 当前阶段

P1：新工程骨架。

当前仓库已经包含全新的 FastAPI 后端、Vue 3 前端和基础 CI，不依赖旧仓库业务模块。P2 才开始实现六类 Project 和真实工作流。

## 后端启动

要求 Python 3.12+。

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

默认由 `VITE_API_BASE_URL` 控制 API 根地址，未配置时使用 `/api/v3`。

## 验证

后端：

```bash
cd backend
python -m compileall app
python -c "from app.main import app; print(app.title)"
pytest
```

前端：

```bash
cd frontend
npm run typecheck
npm test
npm run build
```

CI 会在 `main` push 与 Pull Request 时运行同样的基础验收。
