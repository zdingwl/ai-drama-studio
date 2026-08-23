# F01 — 本机运行 CORS 预检 400 修复

时间：2026-08-23 19:40 +08:00  
Branch：main（未新建分支）

## 现象

用户以 8080 启动 FastAPI：

```text
python -m uvicorn engine.app.main:app --host 127.0.0.1 --port 8080 --reload
```

日志：

```text
GET /api/health 200 OK
OPTIONS /api/projects 400 Bad Request
```

`/favicon.ico 404` 与业务无关，可忽略。

## 判断

后端 8080 已正常响应。`OPTIONS /api/projects 400` 是浏览器 CORS 预检在进入 Controller 前被拒绝。

原实现只允许前端来源：

```text
http://localhost:5173
http://127.0.0.1:5173
```

Vite 如果 5173 被占用会自动选择 5174/5175，因此产生运行时失败。

## 修复

`engine/app/main.py` 改为开发阶段允许：

```text
http://localhost:<任意端口>
http://127.0.0.1:<任意端口>
```

通过 `allow_origin_regex` 实现，不使用 `*`，不放开非本机来源。

新增测试：

```text
test_cors_preflight_allows_local_vite_on_alternate_port
```

覆盖 `Origin: http://localhost:5174` + `POST /api/projects` 预检。

独立 TestClient 验证同样的 CORSMiddleware 配置时，5174 预检返回 200，并回传正确 `Access-Control-Allow-Origin`。

## 8080

当前 `frontend/src/api/http.ts` 已指向：

```text
http://127.0.0.1:8080
```

## 用户下一步

本机：

```text
git pull origin main
```

然后重启 FastAPI；如果 `--reload` 已经监测到拉取变化，也应确认看到 reload 完成。

刷新前端后再次创建项目。预期不再出现：

```text
OPTIONS /api/projects 400 Bad Request
```

而应看到 OPTIONS 200，随后 POST /api/projects 201（创建成功时）。

F01 仍为 IN_PROGRESS，不进入 F02。
