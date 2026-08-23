# Function Contract — 单函数职责模板

> 目标：让函数“值得拆、看得懂、测得清”，而不是为了单函数而无限拆 helper。
>
> **单函数开发 ≠ 每个小函数都写一整页 Contract。**

## 0. 先判断函数等级

### A 级 — 必须完整 Function Contract

符合任一项就属于 A 级：

- 完成一个真实业务用例，例如创建项目、打开项目；
- 改变业务状态，例如 `creating → ready`；
- 写数据库、发布正式文件、删除文件；
- Recovery / Rollback / Migration；
- API Controller / Endpoint；
- 影响 Stable/Frozen Contract；
- 涉及安全边界、幂等、付费 Provider、时间轴等关键规则。

A 级必须完整回答本模板全部内容。

### B 级 — 简化 Contract

典型：

- Repository 单表读写；
- Frontend API wrapper；
- Store action；
- Manifest read/validate；
- 有明确业务语义的路径/校验函数。

B 级至少写清：

```text
业务作用
调用方 / 下游
输入 / 输出
副作用
禁止行为
异常
测试
```

### C 级 — 不单独建立 Contract

典型：

- 日期展示格式化；
- 字符串拼接；
- 私有 JSON helper；
- 表单 reset；
- 单纯 Router back；
- 一眼能理解、无业务状态副作用的私有 helper。

C 级要求：

- 名字清楚；
- 必要时有简体中文注释；
- 有逻辑分支时补单测；
- 不进入项目级 Function Contract 清单。

如果一个 C 级 helper 开始承担业务状态、DB、文件或异常语义，应升级为 A/B 级。

---

# A/B 级函数 Contract

## 1. 基础信息

```text
Function ID:
Function Name:
Function Level: A | B
Feature:
Layer: Controller | Service | Repository | Recovery | Validation | Path | Manifest | Infrastructure | Frontend API | Store | UI
File:
Status: PLANNED | IN_PROGRESS | TESTED
```

## 2. 业务作用

用非技术语言说明：

> 这个函数替用户/系统解决什么真实问题？

不得只把函数名翻译成中文。

## 3. 为什么要独立成函数

说明它隔离了什么职责。

如果回答只是“为了代码整洁”，通常说明不值得单独升为 A/B 级函数。

## 4. 调用关系

### 谁调用它

- 

### 它调用谁

- 

### 调用链位置

```text
上游
→ 当前函数
→ 下游
```

## 5. 输入 Contract

| 参数 | 类型 | 是否必填 | 来源 | 业务含义 | 谁负责校验 |
|---|---|---:|---|---|---|
| | | | | | |

## 6. 输出 Contract

| 输出 | 类型 | 业务含义 |
|---|---|---|
| | | |

## 7. 副作用

必须明确：

```text
DB：读 / 写 / commit / rollback / 无
文件：读 / 写 / rename / 删除 / 无
网络：有 / 无
前端状态：修改什么 / 无
日志：写什么 / 无
```

如果函数名字看起来像 `validate_*` / `get_*`，但实际上会创建目录、commit 或修改状态，必须重命名，不能靠注释掩盖副作用。

## 8. 明确禁止行为

- 不允许修改：
- 不允许调用：
- 不允许越层承担：

典型边界：

- Controller 禁止 SQL / mkdir / Manifest / 业务事务；
- Repository 禁止 commit 业务事务、文件系统和 HTTP；
- Service 负责事务边界和业务编排；
- UI 禁止理解 SQLite / Workspace 内部实现。

## 9. 异常 Contract

| 异常 | 触发条件 | 上层如何处理 | 是否可重试 |
|---|---|---|---:|
| | | | |

## 10. 测试 Contract

### 正常路径

- [ ] 

### 边界

- [ ] 

### 异常

- [ ] 

### 副作用验证

- [ ] 

## 11. 中文代码注释

A 级正式代码必须有简体中文 docstring，至少解释：

```text
业务作用
为什么存在
关键约束
副作用/事务边界
禁止行为/安全边界
重要异常
```

B 级根据复杂度使用 docstring 或紧邻代码注释，但不能只机械翻译函数名。

示例：

```python
def example(...):
    """
    业务作用：...

    为什么存在：...

    关键约束：...

    副作用：...

    禁止行为：...

    Raises:
        ...
    """
```

## 12. 完成标准

- [ ] 函数等级判断正确
- [ ] 业务作用非技术人员可理解
- [ ] 函数名与真实副作用一致
- [ ] 调用方/被调用方明确
- [ ] 输入输出明确
- [ ] DB/File/State 副作用明确
- [ ] 禁止行为明确
- [ ] 异常明确
- [ ] 对应测试明确
- [ ] 中文注释标准明确
