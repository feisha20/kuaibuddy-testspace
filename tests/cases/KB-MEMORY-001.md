# KB-MEMORY-001：公司成员长期记忆功能测试方法与测试用例

- **状态**：草案（基于 `beta` 分支代码实现整理，待结合正式需求与目标环境执行验证）
- **所属模块**：公司成员长期记忆（`user_memory` / Agent 工具 / Web 长期记忆管理）
- **优先级**：P0 / P1 / P2（按具体用例标注）
- **关联任务**：无（可直接用于创建回归任务或本地 Run 引用）
- **需求依据**：基于 `kuaibuddy-projects` `beta` 分支代码实现分析（`base`: `b7d0436`, `6deda08`；`service-agent`: `9f5961d`, `3b72b2b`；`web-agent`: `1dbbe01`；`ui-kuai-buddy`: `401c826`, `e9427a1`），正式产品验收标准待补充
- **参考模板**：[_template.md](_template.md)

---

## 一、功能实现要点与测试范围

1. **数据存储与租户/成员隔离**：
   - 表 `user_memory` 按 `(comp_id, user_id)` 隔离；字段含 `memory_type`（`user` / `feedback` / `project` / `reference`）、`summary`（单行、非空白、≤100 Unicode 码点）、`content`（非空白、≤1000 Unicode 码点）、`source_session_id`、`source_run_id`。
   - 默认容量上限 `agent.memory.max-records = 100`；错误码 `USER_MEMORY_UNAVAILABLE(4055)`、`USER_MEMORY_NOT_FOUND(4056)`、`USER_MEMORY_CAPACITY_EXCEEDED(4057)`。
2. **Agent 对话侧**：
   - 启用门禁：`UserMemoryService.interactive(run) && ctx.get(Execution.class) == null`（仅交互式会话启用，定时任务 `SessionSource.SCHEDULED` 与公共数据执行 `Execution` 不装配）。
   - 装配期注入：`USAGE_PROMPT` + `## 长期记忆索引`（按 `id` 升序的装配快照，写入后当前轮次系统提示词不实时刷新；索引加载失败降级为空索引）。
   - 工具：`memory_read(ids?)`、`memory_save(id?, memory_type, summary, content, replace_ids?)`（`REQUIRES_NEW` 独立事务，支持原子合并）、`memory_delete(id)`。
3. **Web 管理端与前端 UI**：
   - 接口：`GET /web/agent/api/v1/memory/list`（`Cache-Control: no-store`，按 `updatedAt DESC, id DESC`）、`POST /web/agent/api/v1/memory/save`（清空 `sourceSessionId` / `sourceRunId`）、`POST /web/agent/api/v1/memory/delete`。
   - 前端入口：左下角账户菜单第一项「长期记忆」，仅 `!isReadOnly && isLoggedIn && !hideAccount` 可见；支持刷新、关键词本地搜索、分类筛选、新增/编辑（脏表单离开确认、码点计数、失败保留表单）、删除确认、满容量禁用新增。
4. **代码审查发现的待关注点**：
   - `ToolName.java` 中已注册 `memory_save`，未见 `memory_read` 与 `memory_delete` 枚举，需关注对话流工具卡片的展示名称。
   - 目标环境执行前需确认已执行 `user_memory` 建表 DDL，否则将触发 `4055`。

---

## 二、测试方法

1. **API 契约与权限隔离测试**：使用不同企业（`compId`）与同企业不同成员（`userId`）Token 调用 `/web/agent/api/v1/memory/*`，验证越权拦截、单行/码点长度校验（含 Emoji）、`id` 字符串精度、来源字段清空与 100 条容量上限。
2. **Agent 对话闭环与 Langfuse 观测核对**：在交互式会话验证「保存 → 跨会话召回 → 更新/原子合并 → 删除」及「不保存一次性闲聊」；通过 Langfuse 核对 `sysPrompt` 记忆索引注入、`memory_*` 工具入参/返回，以及数据库 `source_session_id` / `source_run_id`。
3. **非交互式门禁验证**：触发定时任务，通过 Langfuse 核对系统提示词未注入记忆索引与记忆工具。
4. **Web UI 交互与双向同步测试**（需获浏览器测试授权后执行）：验证入口显隐、筛选搜索、表单校验与二次确认、错误保留、满容量提示，以及 Web 端与 Agent 对话端双向数据可见性。

---

## 三、测试用例清单

### 1. Agent 对话与工具链路

#### MEM-AGENT-001：明确要求记住偏好并跨会话召回
- **优先级**：P0
- **前置条件**：已登录交互式会话，本人记忆条数 < 100；已授权查看 Langfuse trace。
- **输入数据**：
  - 会话 A：`请记住，我负责售后，以后回复尽量简洁，直接给结论。`
  - 会话 B：`帮我起草一条回复客户的安抚话术，结合我的个人偏好。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 创建会话 A 并发送首轮输入 | Agent 调用 `memory_save`（`memory_type` 为 `user` 或 `feedback`），工具返回成功后向用户确认已保存 | `UserMemoryTool.save`、`USAGE_PROMPT` |
| 2 | 核对数据库 / Web 记忆列表 | 新增 1 条记录，归属当前 `comp_id + user_id`，且 `source_session_id`、`source_run_id` 为会话 A 对应值 | `UserMemoryService.save` |
| 3 | 新建会话 B 并发送追问 | 会话 B 的 `sysPrompt` 包含 `## 长期记忆索引` 及该条摘要；回复风格简洁、直接给结论 | `AgentFactory.assemble`、`UserMemoryService.index` |

- **证据要求**：会话 A/B 的 `sessionId`、`runId`、Langfuse trace 截图/记录、Web 列表截图。

---

#### MEM-AGENT-002：不应保存一次性闲聊或临时任务进度
- **优先级**：P1
- **前置条件**：已登录交互式会话。
- **输入数据**：`我今天下午三点要去开个会，现在帮我总结一下这段话：客户反馈登录超时，请排查。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 发送输入并等待回复 | Agent 正常完成文本总结 | 基础对话能力 |
| 2 | 核对 Langfuse trace 与记忆列表 | 本轮未调用 `memory_save`，记忆总数无变化 | `USAGE_PROMPT` 保存边界 |

- **证据要求**：本轮 `runId` 对应的 Langfuse 工具调用列表、前后记忆总数。

---

#### MEM-AGENT-003：同义更新与原子合并（`replace_ids`）
- **优先级**：P0
- **前置条件**：本人名下存在 2 条相近记忆（假设 ID 为 `A`、`B`，可通过 Web 端或前序对话预置）。
- **输入数据**：`把我之前关于售后回复风格和签名格式的两条记忆合并成一条，统一要求简洁并附带工号 007。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 在新会话发送合并指令 | Agent 先调用 `memory_read` 读取相关正文，再调用 `memory_save` 传入保留 `id` 及 `replace_ids` | `UserMemoryTool.save`、`USAGE_PROMPT` |
| 2 | 核对数据库 / Web 列表 | 保留项内容更新为合并后正文且 `source_*` 刷新；被替代项物理删除，总条数减少 1 | `UserMemoryService.save` |

- **证据要求**：Langfuse 中 `memory_read` 与 `memory_save` 入参、合并前后列表对比。

---

#### MEM-AGENT-004：用户要求忘记指定记忆
- **优先级**：P0
- **前置条件**：存在 1 条测试记忆（如含「工号 007」）。
- **输入数据**：`忘记我之前让你记住的工号 007 那条记忆。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 在新会话发送删除指令 | Agent 调用 `memory_delete(id)` 并返回成功后向用户确认已删除 | `UserMemoryTool.delete` |
| 2 | 核对 Web 列表及历史会话 | 记忆库中该记录已物理删除；此前包含该内容的会话历史仍正常保留 | `UserMemoryService.delete` |

- **证据要求**：Langfuse `memory_delete` 记录、Web 列表、历史会话回读记录。

---

#### MEM-AGENT-005：定时任务会话不装配记忆能力
- **优先级**：P1
- **前置条件**：账号下已配置定时任务，且本人至少有 1 条记忆。
- **输入数据**：定时任务提示词设为 `查询我之前让你记住的个人偏好是什么`。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 触发定时任务执行 1 次 | 任务正常结束，但无法读取本人长期记忆 | `UserMemoryService.interactive` |
| 2 | 查看该次运行的 Langfuse trace | `sysPrompt` 中不包含 `USAGE_PROMPT` 与 `## 长期记忆索引`，工具列表中无 `memory_*` | `AgentFactory.assemble` |

- **证据要求**：定时任务 `runId` 的 Langfuse `sysPrompt` 与工具清单。

---

#### MEM-AGENT-006：记忆容量满时禁止淘汰无关有效记忆
- **优先级**：P1
- **前置条件**：通过接口预置本人记忆至 `100 / 100`。
- **输入数据**：`请新增一条记忆：每周一上午 10 点发送周报。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 发送新增指令 | 若直接新增，`memory_save` 返回 `4057`（记忆容量超限）；Agent 不得擅自调用 `memory_delete` 删除其他有效记忆来腾空间 | `UserMemoryService.requireCapacity`、`USAGE_PROMPT` |

- **证据要求**：Langfuse 工具调用序列及返回状态。

---

#### MEM-AGENT-007：工具展示名称核查（已知风险点）
- **优先级**：P2
- **前置条件**：已登录交互式会话，依次触发 `memory_read`、`memory_save`、`memory_delete`。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 观察对话流中的工具调用展示名称 | `memory_save` 展示「保存记忆」；记录 `memory_read`、`memory_delete` 实际展示文案，确认是否符合产品预期 | `ToolName.java` |

- **证据要求**：前端对话流工具卡片截图。

---

#### MEM-AGENT-008：对话中隐式表达稳定偏好/约定时自动收集（无需明说“记住”）
- **优先级**：P0
- **前置条件**：已登录交互式会话，本人记忆数 < 100。
- **输入数据**：`我平时主要负责华东区医疗客户，以后你给我出周报都默认按“渠道-线索-转化率”三列格式输出。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 发送上述输入（未包含“记住”字眼） | Agent 识别为稳定背景与持续工作约定，主动调用 `memory_save`（`project` 或 `user`） | `USAGE_PROMPT` 保存规则 |
| 2 | 核对记忆列表 | 新增对应记忆，正文简洁自洽 | `UserMemoryService.save` |

- **证据要求**：Langfuse `memory_save` 调用记录、Web 列表截图。

---

#### MEM-AGENT-009：对话中隐式纠正 Agent 时自动记录 `feedback` 并去重更新
- **优先级**：P1
- **前置条件**：已登录交互式会话，本人记忆中已有 1 条“周报输出格式”相关记忆（如 `id=X`）。
- **输入数据**：`不对，周报里不要放转化率，改成“留联率”，以后都按这个口径。`
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 发送纠正指令 | Agent 核对索引后调用 `memory_read`（如需）并沿用原 `id=X` 调用 `memory_save` 更新（或新增 `feedback` 指导），不产生重复条目 | `USAGE_PROMPT` 去重规则 |

- **证据要求**：Langfuse 工具调用记录、记忆列表前后对比。

---

#### MEM-AGENT-010：跨成员 / 跨企业对话使用隔离
- **优先级**：P0
- **前置条件**：准备账号 A（如公司 1 成员 A）与账号 B（同公司成员 B 或跨公司成员 C）。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 账号 A 保存一条特征记忆（如「我的专属暗号是 KST-999」） | 账号 A 记忆库保存成功 | `UserMemoryService.save` |
| 2 | 账号 B 新开对话询问：「我的专属暗号是什么？」 | Agent 无法回答 `KST-999`；Langfuse `sysPrompt` 中不包含账号 A 的记忆索引 | `UserMemoryService.owned`、`AgentFactory.assemble` |

- **证据要求**：账号 A/B 的对话记录、账号 B 的 Langfuse `sysPrompt` 截图/记录。

---

### 2. Web 管理端 API 与权限隔离

#### MEM-API-001：列表排序、防缓存头与人工编辑清空来源
- **优先级**：P0
- **前置条件**：存在 1 条由 Agent 创建的记忆（`source_session_id` 非空），已获取本人有效 Token。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 调用 `GET /web/agent/api/v1/memory/list` | HTTP 200，`code=8`，响应头含 `Cache-Control: no-store`；`memories` 按 `updatedAt` 倒序、`id` 倒序返回，`id` 为字符串，`maxRecords=100` | `MemoryController.list`、`MemoryVO` |
| 2 | 调用 `POST /web/agent/api/v1/memory/save` 编辑该条记录的 `summary` 和 `content` | 返回更新后的 `MemoryVO`；核对数据库该行 `source_session_id` 与 `source_run_id` 均为 `null` | `UserMemoryService.save` |

- **证据要求**：脱敏后的请求/响应报文、数据库字段核对记录。

---

#### MEM-API-002：同企业不同成员与跨企业越权隔离
- **优先级**：P0
- **前置条件**：准备账号 A1（企业 1）、A2（企业 1）、B1（企业 2）的 Token；A1 名下存在记忆 `id=X`。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 分别用 A2、B1 Token 调用 `GET /web/agent/api/v1/memory/list` | 返回列表中均不包含 A1 的记忆 `X` | `UserMemoryService.owned` |
| 2 | 分别用 A2、B1 Token 调用 `POST /web/agent/api/v1/memory/save` 传入 `id=X` | 返回业务错误 `USER_MEMORY_NOT_FOUND(4056)`，A1 数据未被修改 | `UserMemoryService.save` |
| 3 | 分别用 A2、B1 Token 调用 `POST /web/agent/api/v1/memory/delete` 传入 `id=X` | 返回业务错误 `USER_MEMORY_NOT_FOUND(4056)`，A1 数据未被删除 | `UserMemoryService.delete` |

- **证据要求**：三方账号请求与响应报文。

---

#### MEM-API-003：字段合法性与 Unicode 码点边界校验
- **优先级**：P1
- **前置条件**：已获取本人有效 Token，当前记忆数 < 100。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | `save` 传入 `summary` 含 `\n` 或 `\r` | 返回参数错误（`PARAM_ERROR`） | `UserMemoryService.save` |
| 2 | `save` 传入 100 个 Emoji（100 码点）的 `summary` 与 1000 个汉字的 `content` | 保存成功（HTTP 200，`code=8`） | `MemorySaveDTO` `@CodePointLength` |
| 3 | `save` 传入 101 码点 `summary`、1001 码点 `content`、纯空格 `summary` 或 `memoryType="other"` | 均被参数校验拦截，不入库 | `MemorySaveDTO` |

- **证据要求**：各边界入参与响应报文。

---

#### MEM-API-004：Web 端容量上限拦截
- **优先级**：P1
- **前置条件**：当前账号已有 100 条记忆。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | `POST /web/agent/api/v1/memory/save` 不传 `id` 新增第 101 条 | 返回 `USER_MEMORY_CAPACITY_EXCEEDED(4057)` | `UserMemoryService.save` |
| 2 | `POST /web/agent/api/v1/memory/save` 传入已有 `id` 编辑其中 1 条 | 编辑成功 | `UserMemoryService.save` |

- **证据要求**：新增与编辑的请求/响应报文。

---

### 3. Web 前端 UI 交互（需获浏览器测试授权后执行）

#### MEM-UI-001：账户菜单入口显隐控制
- **优先级**：P0
- **前置条件**：分别准备普通登录态、只读态、`hideAccount` 嵌入态访问权限。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 普通登录态进入工作台，点击左下角账户菜单 | 菜单第一项显示「长期记忆」，点击可打开「长期记忆」弹窗 | `SidebarUserFooter/index.tsx` |
| 2 | 切换至只读态或 `hideAccount` 嵌入态查看左下角 | 不显示「长期记忆」入口 | `SidebarUserFooter/index.tsx` |

- **证据要求**：不同状态下的菜单截图。

---

#### MEM-UI-002：搜索、分类筛选与空状态交互
- **优先级**：P1
- **前置条件**：账号下存在 4 种分类共若干条记忆。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 打开「长期记忆」弹窗，依次点击「背景与偏好」「指导与纠正」「工作约定」「资料入口」及「全部」 | 列表实时按分类过滤，顶部展示 `N / 100 条记忆` | `LongTermMemory/index.tsx` |
| 2 | 在搜索框输入仅存在于某条 `content` 中的关键词 | 能正确命中并展示该条记忆（同时匹配摘要与正文） | `useLongTermMemory.ts` |
| 3 | 输入不存在的关键词，再点击「清除筛选」 | 显示「没有匹配的记忆」及「清除筛选」按钮；点击后恢复全部列表 | `LongTermMemory/index.tsx` |

- **证据要求**：筛选与空状态截图。

---

#### MEM-UI-003：表单校验、未保存二次确认与失败保留
- **优先级**：P1
- **前置条件**：打开「长期记忆」弹窗。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 点击「新增记忆」，输入纯空格、100/101 字符摘要、1000/1001 字符正文 | 摘要实时显示 `N / 100`、正文实时显示 `N / 1000`；100/1000 可保存，纯空格或 101/1001 时「保 存」按钮禁用 | `LongTermMemory/index.tsx`、`useLongTermMemory.ts` |
| 2 | 输入有效内容后直接点击「取消」或弹窗关闭按钮 | 弹出「放弃未保存的修改？」确认框；选「继续编辑」返回表单且内容保留 | `useLongTermMemory.ts` |
| 3 | 断网或模拟接口返回失败后点击「保存」 | 表单内展示错误提示，弹窗不关闭，已填内容保留 | `LongTermMemory/index.tsx` |

- **证据要求**：表单校验与确认弹窗截图。

---

#### MEM-UI-004：删除二次确认、满容量提示与双向同步
- **优先级**：P1
- **前置条件**：1. 存在可删记忆；2. 另一场景记忆达到 100 条。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 点击某条记忆删除图标，核对弹窗后点击「确认删除」 | 确认框提示「只删除长期记忆库中的记录，已有会话历史和日志中的文本仍会保留」；确认后列表移除并提示「记忆已删除」 | `memory.zh.json`、`LongTermMemory/index.tsx` |
| 2 | 在满容量（100 条）账号下打开弹窗 | 顶部显示「记忆容量已满，可编辑或删除已有记忆。」，「新增记忆」按钮禁用 | `LongTermMemory/index.tsx` |
| 3 | Web 端新增 1 条记忆后，新开会话向 Agent 询问该内容；再由 Agent 新增 1 条记忆后，在 Web 弹窗点击「刷新记忆」 | 两端数据可互相读取并同步展示 | `useLongTermMemory.ts` |

- **证据要求**：删除确认、满容量提示截图及双向同步记录。

---

### 4. 新增 / 编辑 / 删除边界值专项

#### MEM-BOUNDARY-001：最小长度、前后空格 trim 与多行正文边界
- **优先级**：P1
- **前置条件**：已获取有效 Token / 打开「长期记忆」弹窗，记忆数 < 100。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | `summary` 与 `content` 各输入 1 个有效字符（如 `"a"`）并保存 | 保存成功 | `MemorySaveDTO` |
| 2 | `summary` 输入 `"  前后空格  "`，`content` 输入多行文本（含 `\n`）并保存 | 保存成功；`summary` 自动去除首尾空格，`content` 保留内部换行 | `useLongTermMemory.ts` |
| 3 | `summary` 或 `content` 仅输入空格/制表符 | 前端「保 存」按钮禁用；接口层返回 `1001` 参数错误 | `MemorySaveDTO` |

#### MEM-BOUNDARY-002：非法 ID、重复删除与并发编辑冲突
- **优先级**：P1
- **前置条件**：已获取有效 Token，存在 1 条测试记忆 `id=X`。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 调用 `/save` 或 `/delete` 传入 `id=0`、`-1`、`1.5` 或 `"abc"` | 被 DTO 校验拦截（`PARAM_ERROR` / `1001`） | `MemorySaveDTO`、`MemoryDeleteDTO` |
| 2 | 连续两次调用 `/delete` 删除同一 `id=X` | 第一次成功（`code=8`）；第二次返回 `USER_MEMORY_NOT_FOUND(4056)` | `UserMemoryService.delete` |
| 3 | 删除 `id=X` 后，再调用 `/save` 传入 `id=X` 进行编辑 | 返回 `USER_MEMORY_NOT_FOUND(4056)` | `UserMemoryService.save` |

#### MEM-BOUNDARY-003：特殊字符与 XSS 防护边界
- **优先级**：P2
- **前置条件**：打开「长期记忆」弹窗。
- **步骤与预期结果**：

| 步骤 | 操作 | 预期结果 | 依据 |
|---|---|---|---|
| 1 | 新增记忆，`summary` 与 `content` 包含 `<script>alert(1)</script>`、`' OR 1=1 --` 等字符 | 正常保存并按纯文本转义渲染，不触发脚本执行或数据库异常 | React 默认转义 + MyBatis-Plus 参数化 |

---

## 自动化关联与清理
- **脚本**：无（可基于 `kuaibuddy-preprod` 与 `kb-bug-analyse` 技能补充接口及 Langfuse 校验脚本）。
- **清理**：测试完成后删除测试产生的 `user_memory` 记录；实际执行结果仅写入对应 Run 的 `execution.md` 与 `result.md`，不回填本用例文件。
