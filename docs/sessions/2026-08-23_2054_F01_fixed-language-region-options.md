# F01 固定语言/地区字段改为下拉选择

时间：2026-08-23 20:54 +08:00  
分支：main（未新建分支）

## 用户反馈

用户在真实新建项目弹窗中指出：

> 固定格式的数据改成下拉框，不让填写不规范。

该要求适用于当前 F01 的：

```text
source_language
target_language
target_region
```

## 已实施

### 前端

新增：

```text
frontend/src/constants/project-options.ts
```

统一维护创建项目允许的稳定代码和中文显示名。

`CreateProjectDialog.vue` 已把三个自由输入框改成 select：

```text
原片语言：下拉，可选择自动识别
目标语言：下拉，必选
目标地区：下拉，必选
```

默认仍为：

```text
target_language = en
target_region = US
```

原片语言默认空值，表示暂不指定/后续识别。

当前语言：

```text
zh en ja ko es pt fr de id th vi
```

当前地区：

```text
US GB JP KR ES BR FR DE ID TH VN TW SG
```

### 后端

`engine/app/main.py` 的 `CreateProjectRequest` 不再接受任意字符串：

```text
source_language: LanguageCode | None
target_language: LanguageCode
target_region: RegionCode
```

使用 `Literal` 白名单。

因此即使绕过前端直接请求 API，也不能写入：

```text
Chinese
English
english
USA
美国
中文
```

这类非标准数据。

Schema 校验错误继续返回统一 error envelope：

```text
PROJECT_SOURCE_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_LANGUAGE_UNSUPPORTED
PROJECT_TARGET_REGION_UNSUPPORTED
```

### 测试

新增：

```text
engine/tests/unit/test_project_option_validation.py
```

覆盖：

- 非标准原片语言返回 422；
- 非标准目标语言返回 422；
- 非标准目标地区返回 422；
- 被拒绝请求不能产生项目记录；
- 合法 `zh → ja / JP` 可以正常创建。

## 后续强制规则

以后凡是数据库需要保存稳定枚举/固定代码的字段：

```text
优先 select / radio / card selector
```

不得为了省事直接给自由文本输入框。

如果固定值有前后端边界，则至少做到：

```text
前端限制可选值
+
后端再次校验白名单
```

前端限制不能替代后端校验。

新增语言或地区时必须同步：

```text
frontend/src/constants/project-options.ts
engine/app/main.py
相关测试
```

禁止只改前端或只改后端。

## 当前状态

F01 仍是 `IN_PROGRESS / VERIFICATION_PENDING`。

用户本机同步 main 后需要确认：

```text
三个字段均显示为下拉选择
→ npm run typecheck
→ npm run build
→ pytest -q
→ 实际创建项目
```

不进入 F02。
