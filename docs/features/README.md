# Feature Documents

本目录保存每一个 Feature 的长期规格、实现、测试、验收和 Freeze 文档。

命名固定：

```text
F01-create-project.md
F02-upload-video.md
F03-video-preprocess.md
...
F30-export.md
```

规则：

- 一个 Feature 只维护一份主文档，不按会话重复建 Feature 文档。
- 从 PLANNED 开始创建，开发过程中持续追加实现和测试记录。
- Stable 后写入 Freeze Snapshot。
- 下游 Feature 读取上游 Contract Snapshot，不重新推断上游实现。
- 如果 Stable Feature 必须升级 Contract，优先记录 V2 Contract 和迁移方案，不破坏 V1 语义。
- 每次修改 Feature 代码时，必须同步更新对应 Feature 文档的 Development Log / Change Log。

模板：

- `templates/FEATURE_SPEC_TEMPLATE.md`
- `templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md`
