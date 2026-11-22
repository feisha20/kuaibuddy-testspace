# KuaiBuddy 业务错误码全量映射（BizCode）

> 来源：被测系统 `base` 仓 `src/main/java/cn/kst/kuaibuddy/base/enums/BizCode.java`（`beta` 分支 `6deda08`，最近核对日期：`2026-11-22`）。
> 适用范围：网关及后端各服务统一返回的业务码 `code` 与提示文案 `msg`。

## 快速分段索引

| 错误码分段 | 所属模块 | 跳转 |
|---|---|---|
| `8` | 成功状态 | [成功码](#成功码) |
| `1001–1999` | 通用参数 | [通用参数（1001–1999）](#通用参数10011999) |
| `2001–2999` | 认证、订阅、席位、Exchange 签名 | [认证与授权（2001–2999）](#认证与授权20012999) |
| `3001–3999` | 会话 | [会话（3001–3999）](#会话30013999) |
| `4001–4499` | Agent、岗位、专家、模板、记忆、Skill、账号、灵感/市场、视频、公开内容 | [Agent 与核心业务（4001–4499）](#agent-与核心业务40014499) |
| `5001–5999` | 文件上传与文件库 | [文件与文件库（5001–5999）](#文件与文件库50015999) |
| `6001–6999` | 积分账户与领取 | [积分（6001–6999）](#积分60016999) |
| `7001–7999` | 定时任务与团队任务 | [定时任务（7001–7999）](#定时任务70017999) |
| `8001–8999` | 连接器与 MCP | [连接器与 MCP（8001–8999）](#连接器与-mcp80018999) |
| `9001–9999` | 系统级异常 | [系统（9001–9999）](#系统90019999) |
| `10001–10999` | 渠道机器人与扫码 | [渠道（10001–10999）](#渠道1000110999) |
| `11001–11999` | 广告授权 | [广告授权（11001–11999）](#广告授权1100111999) |

---

## 成功码

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `8` | `SUCCESS` | 操作成功 |

## 通用参数（1001–1999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `1001` | `PARAM_ERROR` | 参数错误 |
| `1002` | `PARAM_MISSING` | 缺少必要参数 |

## 认证与授权（2001–2999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `2001` | `UNAUTHORIZED` | 未登录或登录已过期 |
| `2002` | `FORBIDDEN` | 无权限访问 |
| `2003` | `REFRESH_TOKEN_INVALID` | refreshToken无效或已过期 |
| `2004` | `REFRESH_TOKEN_REUSE_DETECTED` | 检测到异常刷新，请重新登录 |
| `2005` | `SUBSCRIPTION_UNAVAILABLE` | 公司暂无有效订阅 |
| `2006` | `SEAT_UNAVAILABLE` | 当前账号未开通或已停用 KuaiBuddy 产品 |
| `2007` | `AUTH_UPSTREAM_UNAVAILABLE` | 登录服务暂时不可用，请稍后重试 |
| `2008` | `STAFF_KEY_INVALID` | 无效的客服查询Key |
| `2101` | `EXCHANGE_APP_INVALID` | 无效的appId |
| `2102` | `EXCHANGE_SIGN_FAILED` | 签名校验失败 |
| `2103` | `EXCHANGE_EXPIRED` | 请求已过期 |
| `2104` | `EXCHANGE_REPLAY` | 重复请求 |

## 会话（3001–3999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `3001` | `SESSION_NOT_FOUND` | 会话不存在 |

## Agent 与核心业务（4001–4499）

### 基础运行与资源（4001–4006）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4001` | `AGENT_RUN_FAILED` | Agent 执行失败 |
| `4002` | `AGENT_STATE_NOT_FOUND` | AgentState 不存在 |
| `4003` | `AGENT_MESSAGE_NOT_FOUND` | 消息不存在 |
| `4004` | `SKILL_NOT_FOUND` | Skill 不存在 |
| `4005` | `AGENT_NOT_FOUND` | Agent 不存在 |
| `4006` | `AGENT_RUN_ALREADY_ACTIVE` | 当前会话已有进行中的对话 |

### 岗位归属（4008–4019）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4008` | `CAPABILITY_TARGET_NOT_FOUND` | 岗位不存在或不可分配 |
| `4009` | `POSITION_NOT_FOUND` | 岗位不存在 |
| `4010` | `POSITION_DISABLE_BLOCKED_BY_MEMBER` | 岗位存在成员，无法停用 |
| `4011` | `POSITION_BUILTIN_READONLY` | 内置岗位只读 |
| `4013` | `POSITION_DELETE_BLOCKED_BY_MEMBER` | 岗位存在成员，无法删除 |

### 专家与模板（4020–4039）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4020` | `EXPERT_PACKAGE_INVALID` | 专家包无效 |
| `4021` | `EXPERT_EXISTS` | 专家已存在，请更换名称或刷新后重试 |
| `4030` | `TEMPLATE_NOT_FOUND` | 模板不存在 |
| `4031` | `TEMPLATE_BUILTIN_READONLY` | 内置模板只读 |

### 消息卡片状态（4040–4049）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4040` | `AGENT_MESSAGE_STATE_NOT_UPDATABLE` | 该消息不支持状态更新 |
| `4041` | `AGENT_MESSAGE_STATE_CONFLICT` | 消息状态已被更新，请刷新后重试 |

### Agent 运行、沙箱、上下文与长期记忆（4050–4099）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4050` | `AGENT_RUN_CANCELLING` | 会话正在取消中，请稍后重试 |
| `4051` | `AGENT_MAINTENANCE` | 系统正在升级，暂时无法发起新对话，感谢您的理解与耐心等待。 |
| `4052` | `SANDBOX_UNAVAILABLE` | 本轮处理已停止：执行环境已失效，本次修改未完成。再次要求继续时会获取可用环境，临时脚本和未保存文件不保证保留。 |
| `4053` | `SANDBOX_CONNECTION_UNKNOWN` | 本轮处理已停止：执行环境连接异常，刚才操作是否完成暂时无法确认，远端处理也可能仍在进行。系统不会自动重跑；再次要求继续时会先检查环境和已有结果。 |
| `4054` | `AGENT_CONTEXT_BUDGET_EXCEEDED` | 本次执行所需上下文超过模型容量，已停止执行。 |
| `4055` | `USER_MEMORY_UNAVAILABLE` | 记忆读取或维护失败，未确认完成 |
| `4056` | `USER_MEMORY_NOT_FOUND` | 记忆不存在或不可访问 |
| `4057` | `USER_MEMORY_CAPACITY_EXCEEDED` | 记忆容量超限 |

### Skill 与客服账号（4102–4119）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4102` | `SKILL_PACKAGE_INVALID` | Skill 包无效 |
| `4103` | `SKILL_SCOPE_CONFLICT` | Skill 范围与调用者不匹配 |
| `4104` | `SKILL_EXISTS` | Skill 已存在 |
| `4110` | `USER_NOT_FOUND` | 客服账号不存在 |
| `4111` | `ACCOUNT_PROFILE_UPSTREAM_ERROR` | 账号资料服务返回异常 |

### 灵感案例与 Marketplace 导入（4201–4216）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4201` | `INSPIRATION_CASE_NOT_FOUND` | 灵感案例不存在 |
| `4202` | `INSPIRATION_IMPORT_DISABLED` | 灵感案例导入未启用 |
| `4203` | `INSPIRATION_IMPORT_RUNNING` | 灵感案例导入任务正在运行 |
| `4204` | `INSPIRATION_IMPORT_JOB_NOT_FOUND` | 灵感案例导入任务不存在 |
| `4205` | `INSPIRATION_IMPORT_REPORT_NOT_READY` | 灵感案例导入报告尚未生成 |
| `4206` | `MARKETPLACE_SKILL_IMPORT_DISABLED` | Marketplace Skill 导入未启用 |
| `4207` | `MARKETPLACE_SKILL_IMPORT_RUNNING` | Marketplace Skill 导入任务正在运行 |
| `4208` | `MARKETPLACE_SKILL_IMPORT_JOB_NOT_FOUND` | Marketplace Skill 导入任务不存在 |
| `4209` | `MARKETPLACE_SKILL_IMPORT_REPORT_NOT_READY` | Marketplace Skill 导入报告尚未生成 |
| `4210` | `MARKETPLACE_SKILL_ACTIVATION_FAILED` | Marketplace Skill 激活失败 |
| `4211` | `MARKETPLACE_EXPERT_IMPORT_DISABLED` | Marketplace 专家导入未启用 |
| `4212` | `MARKETPLACE_EXPERT_IMPORT_RUNNING` | Marketplace 专家导入任务正在运行 |
| `4213` | `MARKETPLACE_EXPERT_IMPORT_JOB_NOT_FOUND` | Marketplace 专家导入任务不存在 |
| `4214` | `MARKETPLACE_EXPERT_IMPORT_REPORT_NOT_READY` | Marketplace 专家导入报告尚未生成 |
| `4215` | `MARKETPLACE_EXPERT_IMPORT_SNAPSHOT_INVALID` | Marketplace 专家导入快照无效 |
| `4216` | `MARKETPLACE_EXPERT_SKILL_UNAVAILABLE` | 专家关联技能不可用 |

### 视频制作（4301–4318）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4301` | `VIDEO_DISABLED` | 视频制作尚未开通 |
| `4302` | `VIDEO_PLAN_INVALID` | 视频方案无效 |
| `4303` | `VIDEO_NOT_FOUND` | 视频项目或任务不存在 |
| `4304` | `VIDEO_QUOTE_EXPIRED` | 视频报价已过期，请刷新报价并确认 |
| `4305` | `VIDEO_CONFLICT` | 视频状态已变化，请刷新后重试 |
| `4306` | `VIDEO_ASSET_UNAUTHORIZED` | 视频素材未获得相应授权 |
| `4307` | `VIDEO_PROVIDER_UNAVAILABLE` | 视频服务暂不可用 |
| `4308` | `VIDEO_MEDIA_INVALID` | 媒体文件不符合要求 |
| `4309` | `VIDEO_ASSET_REFERENCED` | 文件被视频项目引用，请先删除视频项目 |
| `4310` | `VIDEO_BUDGET_EXHAUSTED` | 视频积分预占不足，请刷新方案并重新确认 |
| `4311` | `VIDEO_IMPORT_RATE_LIMITED` | 视频解析请求较多，请稍后重试或上传视频文件 |
| `4312` | `VIDEO_IMPORT_BUSY` | 视频获取正在排队，请稍后重试或上传视频文件 |
| `4313` | `VIDEO_RESULT_PENDING` | 视频处理结果待核对，请查询原操作，不要重复提交 |
| `4314` | `VIDEO_RESULT_CLOSED` | 视频处理核对期已结束，未扣费，可明确重新发起 |
| `4315` | `VIDEO_ADDRESS_EXPIRED` | 来源视频地址已失效，需要重新解析；成功解析将按当前价格计费 |
| `4316` | `VIDEO_IMPORT_STOPPED` | 已停止，尚未开始的素材未执行 |
| `4317` | `VIDEO_QUALITY_UNAVAILABLE` | 无法取得更高画质，未收取升级导入费 |
| `4318` | `VIDEO_TIMELINE_INVALID` | 视频帧时间戳倒退，需要标准化时间轴 |

### 公开内容查询（4401–4410）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `4401` | `PUBLIC_DATA_DISABLED` | 公开内容查询尚未开放或配置不完整 |
| `4402` | `PUBLIC_DATA_INVALID` | 公开内容查询参数无效 |
| `4403` | `PUBLIC_DATA_NOT_FOUND` | 公开内容查询不存在 |
| `4406` | `PUBLIC_DATA_UNAVAILABLE` | 公开内容查询暂不可用，请查看原查询状态 |
| `4407` | `PUBLIC_DATA_PENDING` | 原查询尚待核对，请查询原操作 |
| `4408` | `PUBLIC_DATA_EXPIRED` | 查询结果或分页已过期，请发起新的查询 |
| `4409` | `PUBLIC_DATA_RATE_LIMITED` | 公开内容查询请求较多，本次未执行 |
| `4410` | `PUBLIC_DATA_STOPPED` | 采集已停止，未开始的查询不收费 |

## 文件与文件库（5001–5999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `5001` | `FILE_EMPTY` | 上传文件为空 |
| `5002` | `FILE_TOO_LARGE` | 文件大小超出限制 |
| `5003` | `FILE_UPLOAD_FAILED` | 文件上传失败 |
| `5004` | `FILE_FORMAT_NOT_SUPPORTED` | 文件格式不支持 |
| `5005` | `LIBRARY_QUOTA_EXCEEDED` | 文件库配额不足 |
| `5006` | `LIBRARY_NOT_FOUND` | 文件不存在 |
| `5007` | `LIBRARY_FORBIDDEN` | 无权操作该文件 |
| `5008` | `LIBRARY_FILE_NOT_FOUND` | 源文件不存在 |

## 积分（6001–6999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `6001` | `POINTS_INSUFFICIENT` | 积分不足，请明天领取后再使用 |
| `6002` | `POINTS_ALREADY_CLAIMED` | 今日积分已领取 |
| `6003` | `POINTS_ACCOUNT_MISSING` | 积分账户不存在，请先开通产品 |

## 定时任务（7001–7999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `7001` | `SCHEDULED_TASK_NOT_FOUND` | 定时任务不存在 |
| `7002` | `SCHEDULED_TASK_DELETED` | 定时任务已删除 |
| `7003` | `TEAM_TASK_NOT_FOUND` | 团队定时任务不存在 |
| `7004` | `TEAM_TASK_MANAGED` | 企业任务由管理员维护，成员仅可查看 |
| `7005` | `TEAM_TASK_RESUME_BLOCKED` | 计划已停用、成员已移出或成员资格无效，无法恢复 |
| `7006` | `TEAM_TASK_MEMBER_UNAVAILABLE` | 新增或移回的成员须已开通且启用 KuaiBuddy |

## 连接器与 MCP（8001–8999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `8001` | `CONNECTOR_NOT_FOUND` | 连接器未配置 |
| `8002` | `CONNECTOR_TEST_FAILED` | 连接器测试失败 |
| `8003` | `CONNECTOR_TYPE_INVALID` | 不支持的连接器类型 |
| `8004` | `MCP_CONFIG_INVALID` | MCP 配置不受支持 |
| `8005` | `MCP_RETEST_REQUIRED` | 配置已变化或测试已过期，请重新测试 |
| `8006` | `MCP_CONFLICT` | 连接器已被修改，请重新打开后编辑 |
| `8007` | `MCP_AUTH_FAILED` | MCP 认证失败，请重新认证或替换令牌 |
| `8008` | `MCP_TIMEOUT` | MCP 网络阶段超过 30 秒，请手动重试 |
| `8009` | `MCP_UNAVAILABLE` | MCP 连接器不可用 |
| `8010` | `MCP_TOOL_CHANGED` | 工具定义已变化，请重新测试并保存授权 |
| `8011` | `MCP_DISABLED` | 连接器已停用，后续调用已拦截 |
| `8012` | `MCP_TOOL_UPDATED` | 工具已更新，本次执行暂不可用；下一次执行将重新获取，无需重新授权 |

## 系统（9001–9999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `9001` | `SYSTEM_ERROR` | 系统繁忙，请稍后重试 |

## 渠道（10001–10999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `10001` | `CHANNEL_NOT_FOUND` | 渠道机器人未配置 |
| `10002` | `CHANNEL_TYPE_INVALID` | 不支持的渠道类型 |
| `10003` | `CHANNEL_SCAN_CREATE_FAILED` | 扫码发起失败 |
| `10004` | `CHANNEL_SCAN_VERIFY_UNSUPPORTED` | 该渠道不支持扫码验证码 |
| `10005` | `CHANNEL_SCAN_SESSION_NOT_FOUND` | 扫码会话不存在或已过期 |

## 广告授权（11001–11999）

| Code | 枚举名 | 默认消息（`msg`） |
|---|---|---|
| `11001` | `AD_CHANNEL_INVALID` | 不支持的广告渠道 |
| `11002` | `AD_AUTH_UPSTREAM_UNAVAILABLE` | 广告授权服务暂时不可用，请稍后重试 |
| `11003` | `AD_AUTH_UPSTREAM_ERROR` | 广告授权接口返回异常 |
