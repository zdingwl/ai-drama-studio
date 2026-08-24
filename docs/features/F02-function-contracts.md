# F02 — 上传原视频：核心函数与 Controller 详细职责

Feature ID: F02  
Status: PLANNED / WAITING_USER_CONFIRMATION  
Depends On: F01 — 创建项目（STABLE / FROZEN）

> 本文件专门解释 F02 的 6 个核心后端函数和 2 个 HTTP Controller 到底是干什么的。
> 目标是开发时不用猜函数名：能直接知道它在完整业务流程中的位置、输入、输出、副作用、失败边界和禁止行为。
>
> F02 仍然只保留 6 个核心业务函数，不因为补详细说明继续拆成几十个 helper。

---

# 1. 先看完整业务流程

用户在项目里点击“开始导入”以后，真实流程是：

```text
浏览器选择视频
↓
POST /api/projects/{project_id}/source-video
↓
import_source_video_api()
↓
import_source_video()
↓
验证 F01 Project 可以正常打开
↓
确认这个 Project 还没有 Source Video
↓
generate_source_video_id()
↓
DB 创建 source_videos(importing)
↓
copy_upload_to_staging()
↓
得到 file_size_bytes + sha256
↓
probe_source_video()
↓
得到 duration / codec / width / height / fps / audio 等 metadata
↓
把 staging 目录发布成正式 source/SOURCE_xxx/
↓
DB 更新为 ready
↓
返回 SourceVideoDTO
↓
前端展示原片信息
```

软件重启时另外执行：

```text
recover_source_video_imports()
```

用于处理上一次程序退出时残留的 `importing` Source。

页面刷新或重新进入“视频导入”页时：

```text
GET /api/projects/{project_id}/source-video
↓
get_source_video_api()
↓
get_source_video()
```

只读取已经导入完成的 Source Video。

---

# 2. `generate_source_video_id()`

## 它到底是干什么的

给每一份正式导入的原视频生成一个**稳定的 Source Video 业务 ID**。

格式：

```text
SOURCE_<32位UUID4小写hex>
```

例如：

```text
SOURCE_86f767c94f2c4f96a1676ce36f615406
```

这个 ID 后面会同时用于：

```text
source_videos.id
source/SOURCE_<UUID>/ 目录名
F03/F04/... 下游引用 Source Video
日志/错误定位
```

## 为什么要单独存在

不能用原始文件名做 ID，因为用户可能上传：

```text
第一集最终版.mp4
1.mp4
final-final-2.mov
```

文件名：

- 可能重复；
- 可以包含中文/空格/特殊字符；
- 不是稳定业务身份；
- 以后即使展示名变化，也不能让下游引用失效。

所以 Source Video 必须有自己的稳定 ID。

## 谁调用它

只由：

```text
import_source_video()
```

调用。

Controller 和前端都不能自己生成 Source ID。

## 输入

```text
无业务输入
```

内部使用 Python UUID4。

## 输出

```text
str
```

例如：

```text
SOURCE_d4779154615444409dc5745e62884318
```

## 副作用

```text
无
```

不访问：

- SQLite；
- Workspace；
- FFprobe；
- 网络。

## 明确禁止

不能：

```text
用 project_id 拼出 Source ID
用文件名生成 Source ID
查询数据库
创建目录
写 source_videos
```

数据库主键仍然是最终极小概率冲突保护。

## 失败

UUID4 正常情况下不产生业务错误。

## 测试

至少：

```text
SOURCE_ 前缀正确
后缀 32 位小写 hex
可解析为 UUID4
批量生成不重复
```

---

# 3. `copy_upload_to_staging(upload_file, staging_file)`

## 它到底是干什么的

把浏览器传过来的**大视频文件安全写到项目临时目录**，并在写入过程中同时计算：

```text
真实文件大小
SHA-256
```

这是 F02 真正负责“搬运视频字节”的函数。

## 为什么要单独存在

视频可能几百 MB、几个 GB。

绝对不能：

```python
content = await upload_file.read()
```

一次把整个视频吃进内存。

这个函数必须按固定 chunk 循环：

```text
读取一块
→ 写一块
→ 更新 SHA-256
→ 累计字节数
→ 下一块
```

因此文件复制、大小统计、Hash 计算只遍历视频一次。

## 谁调用它

只由：

```text
import_source_video()
```

调用。

Recovery 不应该重新走浏览器 UploadFile。

## 输入

### `upload_file`

FastAPI `UploadFile`，代表浏览器正在上传的视频流。

### `staging_file`

系统已经计算好的临时目标路径，例如：

```text
<workspace>/source/.staging/SOURCE_xxx/original.mp4
```

调用者必须先确定该路径属于当前 Source ID。

## 输出

建议返回简单结果对象：

```text
CopiedFileInfo
├─ file_size_bytes
└─ sha256
```

例如：

```text
file_size_bytes = 838493244
sha256 = "b20c...91ad"
```

## 它会修改什么

只允许修改：

```text
本次 Source ID 对应的 staging 文件
```

它负责：

```text
创建/打开 staging_file
分块写入
flush
close
必要时 fsync
```

## 它不负责什么

明确不负责：

```text
不查询 Project
不生成 Source ID
不写 source_videos 表
不把 DB 改 ready
不调用 FFprobe
不决定是不是视频
不 rename 到 final
不生成 proxy/audio/thumbnail
```

也就是说：

> 它只保证“上传来的字节完整写到 staging，并告诉上层大小和 Hash”。

## 失败行为

可能失败：

```text
上传流读取失败
磁盘空间不足
目录不可写
写盘失败
0 字节文件
```

失败时：

- 关闭文件句柄；
- 抛出明确异常给 `import_source_video()`；
- 最终是否删除 staging / importing DB row，由 `import_source_video()` 统一决定。

它自己不能擅自递归删除目录。

## 测试

至少：

```text
小文件内容完全一致
大于一个 chunk 的文件完整写入
file_size_bytes 正确
SHA-256 正确
0 字节拒绝
读取/写入异常能够上抛
不能一次 read 整文件
```

---

# 4. `probe_source_video(path)`

## 它到底是干什么的

使用本机 **FFprobe** 判断 staging 文件是不是系统可以读取的真实视频，并把 FFprobe 的复杂 JSON 转换成系统后续可以稳定使用的 `SourceVideoMetadata`。

它解决的是：

> “这个文件到底是不是视频？有多长？什么编码？尺寸多少？FPS 是多少？有没有音频？”

## 为什么需要它

不能只看：

```text
.mp4
.mov
.mkv
浏览器 MIME
```

因为一个叫 `abc.mp4` 的文件完全可能是损坏文件甚至文本文件。

F02 必须以 FFprobe 实际解析结果作为媒体真实性判断。

## 谁调用它

主要由：

```text
import_source_video()
recover_source_video_imports()
```

调用。

正常导入时 Probe staging 文件；Recovery 时可能重新 Probe 已发布的 final 原片。

## 输入

```text
path: Path
```

必须是系统已经确定的本地文件路径。

## 调用外部程序

等价于：

```text
ffprobe
-show_format
-show_streams
-of json
<path>
```

实现必须使用 subprocess 参数数组：

```python
subprocess.run(["ffprobe", ...])
```

禁止：

```python
shell=True
```

也禁止自己字符串拼 Shell 命令。

## 它需要从 FFprobe 做什么

### 主视频流

```text
排除 attached_pic
→ 优先 default=1
→ 否则第一个普通 video stream
```

### 主音频流

```text
优先 default=1
→ 否则第一个 audio stream
→ 没有音频允许
```

### 时间

转换为权威整数微秒：

```text
duration_us
source_start_time_us
```

不能把 float 秒原样持久化为权威值。

### FPS

保存：

```text
fps_num
fps_den
```

例如：

```text
30000 / 1001
```

不能只保存 `29.97`。

## 输出

返回：

```text
SourceVideoMetadata
├─ container_format
├─ duration_us
├─ source_start_time_us
├─ video_stream_index
├─ video_codec
├─ width
├─ height
├─ fps_num
├─ fps_den
├─ audio_stream_index
├─ audio_codec
├─ audio_sample_rate
└─ audio_channels
```

## 基础合法性判断

至少必须满足：

```text
FFprobe exit code 成功
存在普通 video stream
width > 0
height > 0
duration_us > 0
```

没有 audio stream：

```text
允许
```

因为无声视频仍然可以是合法 Source Video。

## 它会修改什么

```text
什么都不修改
```

它是“读取 + 解析 + 校验”函数。

## 明确禁止

不能：

```text
不能调用 FFmpeg 转码
不能修改原片
不能生成 proxy.mp4
不能生成 audio.wav
不能生成 thumbnail.jpg
不能写数据库
不能把 Source 标记 ready
```

## 失败

需要区分：

```text
FFprobe 程序不存在
FFprobe 执行失败
JSON 无法解析
不存在视频流
视频宽高/时长非法
```

最终映射成 F02 稳定业务错误，例如：

```text
SOURCE_VIDEO_FFPROBE_UNAVAILABLE
SOURCE_VIDEO_PROBE_FAILED
SOURCE_VIDEO_UNSUPPORTED
```

## 测试

至少：

```text
正常 MP4 metadata
MOV/MKV metadata
无音频视频
default stream 选择
attached_pic 不当主视频
30000/1001 FPS
source start_time
损坏文件
纯音频文件
FFprobe 不存在
```

---

# 5. `import_source_video(project_id, upload_file)`

## 它到底是干什么的

这是 F02 最重要的**核心业务总调度函数**。

用户点击：

```text
开始导入
```

真正完成整套业务的就是它。

Controller 只把 HTTP 文件交给它；至于：

- 当前 Project 能不能导入；
- Source ID 是多少；
- DB 什么时候写 importing；
- 视频写到哪里；
- Hash 怎么算；
- FFprobe 是否通过；
- 什么时候发布为正式原片；
- 什么时候 DB 才能 ready；
- 出错要回滚什么；

全部由这个函数决定。

## 为什么必须只有一个总调度

如果 Controller、文件函数、Repository 各自决定一点状态，就很容易出现：

```text
DB 说 ready
但是文件没写完
```

或者：

```text
文件已经正式落盘
Controller 又因为异常把它删了
```

所以创建 Source Video 的事务边界只能有一个负责人。

## 谁调用它

只由：

```text
import_source_video_api()
```

调用。

前端不会直接调用这个 Python 函数。

## 输入

### `project_id`

F01 冻结 Project ID。

### `upload_file`

FastAPI UploadFile。

至少使用：

```text
filename
content_type（仅提示，不作为真实性判断）
stream
```

## 完整执行步骤

### 第 1 步：验证 Project

必须确认：

```text
projects 中存在
status = ready
Workspace 存在
project.json 合法
project.json.project_id == project_id
```

不能因为 API URL 里有 Project ID 就直接相信。

### 第 2 步：检查“一项目一原片”

查询 `source_videos`。

只要当前 Project 已存在：

```text
importing
或
ready
```

都拒绝第二次导入：

```text
SOURCE_VIDEO_ALREADY_EXISTS
```

### 第 3 步：生成 Source ID

调用：

```text
generate_source_video_id()
```

### 第 4 步：建立 DB 恢复锚点

先创建：

```text
source_videos.status = importing
```

并提交。

这样如果程序在后面突然退出，启动 Recovery 才知道这次导入没有完成。

### 第 5 步：确定安全内部路径

例如用户文件：

```text
我的短剧 第1集.Final.MP4
```

DB 保留原始名字用于展示：

```text
original_filename
```

但内部文件使用：

```text
source/.staging/SOURCE_xxx/original.mp4
```

不能直接用用户文件名做内部目录结构。

### 第 6 步：流式复制

调用：

```text
copy_upload_to_staging()
```

得到：

```text
file_size_bytes
sha256
```

### 第 7 步：真实媒体验证

调用：

```text
probe_source_video()
```

只有 FFprobe 证明它是可读取视频，才允许继续。

### 第 8 步：发布文件

把：

```text
source/.staging/SOURCE_xxx/
```

同盘原子/安全 rename 成：

```text
source/SOURCE_xxx/
```

这一步以后代表：

> 原始视频字节已经正式进入 Project Workspace。

### 第 9 步：DB 标记 ready

只有 final 文件已经存在并通过 FFprobe 后，才更新：

```text
relative_path
file_size_bytes
sha256
所有 metadata
status = ready
```

### 第 10 步：返回 DTO

返回完整：

```text
SourceVideoDTO
```

给 Controller → 前端。

## 文件/数据库副作用

它会：

```text
读取 F01 projects
写 source_videos
创建 source/.staging/SOURCE_xxx
最终创建 source/SOURCE_xxx/original.ext
```

## 失败边界

### Final 发布之前失败

例如：

```text
磁盘写失败
0 字节
FFprobe 失败
不是视频
```

处理：

```text
只清理本 Source ID 的 staging
删除本次 importing row
```

用户可以重新上传。

### Final 已发布以后失败

例如：

```text
文件已经 rename 到 source/SOURCE_xxx/
但 DB ready commit 失败
```

处理：

```text
不删除 final 视频
保留 importing row
返回 SOURCE_VIDEO_FINALIZATION_PENDING
```

下次启动由 Recovery 恢复。

这是非常重要的安全边界。

## 明确禁止

不能：

```text
覆盖已有 ready Source
删除已有 Source
替换 Source
转码视频
抽 WAV
做 Thumbnail
做 Proxy
做 Shot Detection
修改 F01 project.json V1
修改 F01 Project ID
```

## 测试

这是 F02 集成测试重点，至少：

```text
正常导入 → ready
Project 不存在
Project Workspace 损坏
第二次导入拒绝
0 字节失败且无残留 ready
损坏视频失败
写盘失败 rollback
FFprobe 失败 rollback
final 发布后 DB 失败保留 final
Source 原片字节与上传文件一致
SHA-256 一致
```

---

# 6. `get_source_video(project_id)`

## 它到底是干什么的

给“视频导入”页面读取**这个项目已经正式导入完成的 Source Video**。

它解决：

```text
页面刷新
重新进入项目
软件重启
```

以后页面仍然知道：

> 这个项目已经有一份原片，不应该重新显示上传入口。

## 谁调用它

由：

```text
get_source_video_api()
```

调用。

## 输入

```text
project_id
```

## 输出

有 ready Source：

```text
SourceVideoDTO
```

没有 Source：

```text
None
```

Controller 会转换成 JSON：

```json
null
```

## 它读取什么

```text
source_videos
```

原则上只返回：

```text
status = ready
```

正式 Source。

## 它不做什么

明确：

```text
不重新 FFprobe
不重新计算 SHA-256
不读完整视频内容
不修改 last_opened_at
不修改 source_videos
不修复 importing
不检查/生成 F03 产物
```

这是一个正常页面读取函数，不应该每次刷新页面都重新扫描几个 GB 的视频。

## 如果 DB ready 但文件被用户手工删了怎么办

F02 需要明确暴露完整性错误，不能假装成功。

建议：

```text
读取 DB ready
→ 解析 workspace + relative_path
→ 检查正式文件至少仍存在且是普通文件
```

如果缺失：

```text
SOURCE_VIDEO_FILE_MISSING
```

但不在 GET 时自动删除 DB 行，也不自动重新上传。

## 测试

```text
无 Source → None
ready → DTO
importing 不作为 ready 返回
ready DB + 文件存在 → 正常
ready DB + 文件缺失 → 明确错误
函数调用不改变数据库状态
```

---

# 7. `recover_source_video_imports()`

## 它到底是干什么的

在软件启动时处理上一次异常退出留下的：

```text
source_videos.status = importing
```

它不是普通页面接口，而是**崩溃恢复函数**。

用户可能在：

```text
上传到一半时关程序
FFprobe 时断电
final 文件已经发布但 DB 还没来得及改 ready
```

如果没有 Recovery，项目会永久卡在“正在导入”。

## 谁调用它

由 FastAPI Application 启动生命周期调用。

顺序建议：

```text
init_database()
→ recover_creating_projects()        # F01
→ recover_source_video_imports()      # F02
→ 应用开始接收请求
```

## 输入

正常情况下无用户输入。

读取所有：

```text
source_videos.status = importing
```

## 对每一条 importing 如何处理

### 情况 A：final 文件已经存在且合法

```text
source/SOURCE_xxx/original.ext 存在
↓
probe_source_video(final)
↓
合法
↓
补齐 metadata
↓
status = ready
```

用途：恢复“文件已经发布但 DB final commit 失败”。

### 情况 B：只有系统 staging

```text
source/.staging/SOURCE_xxx/
```

存在，final 不存在。

因为 F02 V1 不做断点续传：

```text
安全清理本 Source ID staging
删除 importing row
```

让用户重新导入。

### 情况 C：DB importing，但磁盘什么都没有

说明导入还没真正写出文件或已经被中断清理。

处理：

```text
删除 importing row
```

### 情况 D：发现未知文件或目录结构不符合预期

例如 staging 里出现系统不认识的文件：

```text
user-note.txt
unknown.bin
```

处理：

```text
不递归删除
保留 DB importing
记录高优先级日志
```

宁可留下待人工处理状态，也不能误删用户文件。

### 情况 E：final 存在但 FFprobe 失败

不能自动删除 final，因为已经无法百分百确认它是否是用户需要保留的文件。

处理建议：

```text
保留 final
保留 importing
记录错误
```

F02 不实现 Repair UI。

## 输出

建议返回恢复统计，便于测试和日志：

```text
{
  "recovered": n,
  "removed": n,
  "preserved": n
}
```

不是给普通前端页面使用。

## 明确禁止

不能：

```text
删除 ready Source
覆盖 final Source
递归删除 source/
递归删除 Project Workspace
把未 Probe 的文件直接标 ready
尝试续传浏览器上传
```

## 测试

至少覆盖 A–E 五类情况。

---

# 8. `get_source_video_api(project_id)`

## 它到底是干什么的

这是“视频导入页面加载时”的 HTTP 入口。

浏览器打开：

```text
/projects/:projectId/source-video
```

前端首先请求：

```http
GET /api/projects/{project_id}/source-video
```

Controller 接到请求后只做：

```text
读取 URL project_id
↓
调用 get_source_video(project_id)
↓
有数据 → 返回 SourceVideoDTO
无数据 → 返回 null
```

## 为什么需要这个 API

因为前端不能自己直接读 SQLite，也不能靠之前页面内存判断项目有没有原片。

软件重启以后 Pinia 状态会丢失，必须从后端持久化数据恢复。

## 输入

HTTP Path：

```text
project_id
```

## 输出

有 Source：

```http
200 OK
```

```json
{
  "id": "SOURCE_...",
  "project_id": "PROJECT_...",
  "original_filename": "episode01.mp4",
  "status": "ready"
}
```

实际 DTO 还包含完整 metadata。

无 Source：

```http
200 OK
null
```

## Controller 明确不能做

不能在这里：

```text
SQL SELECT
Path.exists
FFprobe
SHA-256
修改 DB
Recovery
```

这些都属于业务函数。

## 错误

例如：

```text
PROJECT_NOT_FOUND
PROJECT_WORKSPACE_MISSING
SOURCE_VIDEO_FILE_MISSING
```

由统一异常处理器转换成稳定 HTTP error envelope。

## 测试

```text
无 Source → 200 null
有 Source → 200 DTO
文件丢失 → 正确业务错误
Controller 不产生业务副作用
```

---

# 9. `import_source_video_api(project_id, file)`

## 它到底是干什么的

这是用户点击“开始导入”时的 HTTP 入口。

前端发送：

```http
POST /api/projects/{project_id}/source-video
Content-Type: multipart/form-data
```

其中：

```text
file = 用户选择的原视频
```

Controller 的角色可以理解为：

> “接待浏览器上传，然后把 UploadFile 原封不动交给真正的业务总调度 `import_source_video()`。”

## 输入

### URL

```text
project_id
```

### multipart

```text
file: UploadFile
```

## 它实际执行什么

只允许：

```text
1. FastAPI 解析 multipart
2. 检查 HTTP 层 file 参数是否存在
3. 调用 import_source_video(project_id, file)
4. 成功返回 SourceVideoDTO + 201
5. 业务异常交给统一 exception handler
```

## 它为什么不能自己写文件

如果 Controller 自己做：

```text
mkdir
while file.read
hash
FFprobe
SQL
rename
```

那么真正的创建 Source 业务会散落在 HTTP 层，Recovery 和未来 Electron 本地调用就无法复用同一套规则。

所以 Controller 绝对不能承载媒体导入业务。

## 输出

成功：

```http
201 Created
```

返回：

```text
SourceVideoDTO
```

## 常见错误

```text
404 Project 不存在
409 Project 已经有 Source
422 空文件/非法视频/Probe 失败
503 FFprobe 不可用
500 导入失败/最终 DB 状态待恢复
```

仍然使用 F01 已冻结的统一 envelope：

```json
{
  "error": {
    "code": "SOURCE_VIDEO_UNSUPPORTED",
    "message": "选择的文件不是系统可读取的视频"
  }
}
```

## Controller 明确禁止

```text
不生成 Source ID
不决定 staging/final 路径
不创建 source 目录
不读整个视频到内存
不算 SHA-256
不调用 FFprobe
不 SQL
不 commit/rollback
不做 Recovery
```

## 关于上传进度

Controller 不需要新增“进度 API”。

浏览器通过：

```text
XMLHttpRequest.upload.onprogress
```

获取客户端 → FastAPI 的传输进度。

上传字节达到 100% 后，如果服务器还在 FFprobe/最终提交，前端状态切换为：

```text
正在读取媒体信息…
```

直到 POST 最终返回。

## 测试

```text
multipart 正常视频 → 201
缺少 file → 422
第二次上传 → 409
非法视频 → 对应业务错误
超大文件实现不依赖整文件内存读取
```

---

# 10. 这 8 个入口之间的职责边界

最终开发时应该始终保持：

```text
HTTP Controller
        ↓
Business Service
        ↓
文件 / FFprobe / DB 操作
```

具体关系：

```text
GET source-video
└─ get_source_video_api()
   └─ get_source_video()

POST source-video
└─ import_source_video_api()
   └─ import_source_video()
      ├─ generate_source_video_id()
      ├─ copy_upload_to_staging()
      └─ probe_source_video()

Application Startup
└─ recover_source_video_imports()
   └─ probe_source_video()    # 仅 final 已存在需要恢复时
```

这意味着：

### Controller 负责

```text
HTTP 输入
HTTP 输出
HTTP 状态码
Schema / multipart 边界
```

### `import_source_video()` 负责

```text
完整“导入一份原片”的业务事务
DB 状态
文件生命周期
失败回滚
发布点
```

### `copy_upload_to_staging()` 负责

```text
纯视频字节搬运 + size/hash
```

### `probe_source_video()` 负责

```text
纯媒体读取/验证
```

### `get_source_video()` 负责

```text
读取已经完成的 Source
```

### `recover_source_video_imports()` 负责

```text
异常退出恢复
```

这样以后看到函数名，不需要再猜它为什么存在。

---

# 11. 仍然不单独升级为正式函数 Contract 的小 helper

以下实现时可能自然出现，但不要为了“函数越多越专业”把它们全部写成核心架构：

```text
sanitize_extension()
parse_fraction()
seconds_to_microseconds()
select_default_video_stream()
select_default_audio_stream()
format_ffprobe_error()
resolve_source_paths()
cleanup_owned_staging()
```

原则：

- 如果只是几行纯转换/路径代码，可以作为私有 helper；
- 写清中文注释；
- 有边界逻辑就写单测；
- 不再为每个 helper 建一层 Service/Repository/Contract。

F02 核心职责仍然就是本文的 6 个业务函数 + 2 个 Controller。
