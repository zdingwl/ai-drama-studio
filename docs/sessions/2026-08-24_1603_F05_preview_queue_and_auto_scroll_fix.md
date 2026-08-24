# F05 缩略图队列与当前镜头自动滚动修正

时间：2026-08-24 16:03 +08:00  
分支：main

## 用户现场截图发现

F05 三栏工作台主体、Proxy 播放器、31 个 Final Shot、右侧编辑区均已正常显示，但截图暴露两个真实问题：

```text
1. 左侧所有 Shot 缩略图显示破图
2. 播放/选择已经到 #031 时，左侧列表仍停留在 #001 附近
```

## 本轮修正

### 1. 预览图不再直接并发几十个 FFmpeg 请求

旧页面给每个 `<img>` 直接设置 `/shot-workbench/frame` URL。31 个 Shot + 当前镜头 5 张关键帧会在页面渲染时产生大量并发本地抽帧请求。

改为：

```text
前端预览队列
→ fetch 单张 frame
→ 失败自动重试一次
→ 成功转 blob URL
→ 同一 Source 时间只生成一次
→ 页面离开时 revoke blob URL
```

Shot 缩略图与当前镜头关键帧分别有队列 generation，镜头切换后旧关键帧队列自动停止。

如果 frame 后端仍返回错误，页面不再显示浏览器破图图标，而显示“预览失败”，并在顶部给出真实 HTTP/后端业务错误提示，便于下一轮定位。

### 2. Shot 缩略图改取镜头中间帧

旧逻辑：

```text
start + 最多 50ms
```

太靠近自动切镜边界，容易落在转场/解码边缘。

新逻辑：

```text
shot midpoint
```

更适合人工快速识别镜头内容。

### 3. 5 关键帧增加安全边距

首/尾预览向镜头内部保留最多 40ms 安全边距，避免在精确 EOF / Cut 边界附近请求到无可解码帧；25% / 50% / 75% 仍按内部安全区均匀取样。

### 4. 当前 Shot 自动保持可见

`selectedShotId` 变化后：

```text
nextTick
→ 找到 data-shot-id 对应卡片
→ scrollIntoView({ block: 'nearest' })
```

所以播放器跨镜、点击 Timeline 或点击 Shot 后，左栏会自动跟随当前 Final Shot。

## 修改文件

```text
frontend/src/views/ShotWorkbench.vue
frontend/src/shot-workbench.css
```

F04 Stable/Frozen Contract、F05 Final Shot 数据库与编辑语义均未修改。

## 当前验收

用户本机执行：

```powershell
cd D:\ai-drama-studio
git pull
cd frontend
npm run typecheck
npm run build
```

刷新 F05 后检查：

```text
缩略图应逐张从“生成中”变为画面
关键帧应逐张出现
播放到后部镜头时左栏自动滚动
```

如果页面出现“部分预览图未生成”，把该提示和后端 `/shot-workbench/frame` 对应日志发回；提示现在会包含可定位的业务错误，不再只看到破图。
