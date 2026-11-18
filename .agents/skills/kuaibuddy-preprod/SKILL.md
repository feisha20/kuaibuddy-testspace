---
name: kuaibuddy-preprod
description: 在 KuaiBuddy 指定环境（如测试环境 .env.test、预生产环境 .env.preprod 等）登录、执行获授权的对话测试或回读会话时使用，使用项目本地配置和运行目录。
---

# KuaiBuddy 多环境登录与对话测试

读取仓库 AGENTS.md、README.md 和相关任务资产。此技能适配所有环境（测试、预生产等）：**必须按用户明确指定的环境选择对应配置文件**，未明确指定时不擅自猜测或跨环境复用；不依赖浏览器。

## 登录与凭据

- 需要 Node.js 18 及以上，无第三方依赖。脚本 `scripts/kb_e2e.js` 通过 `KB_ENV_FILE` 指定环境配置文件（未指定时默认读取仓库根目录 `.env.preprod`），也可通过 `KB_URL`、`KB_COMPANY_ID`、`KB_USERNAME`、`KB_PASSWORD` 覆盖对应项。不得回退读取其他项目的配置。
  - **测试环境**：`KB_ENV_FILE=.env.test`
  - **预生产环境**：`KB_ENV_FILE=.env.preprod`（或默认）
  - **其他环境**：`KB_ENV_FILE=.env.<env>`（按用户指定的环境文件）
- 配置文件字段为 `url`、`companyid`、`usrname`、`password`。密码、令牌和账号不写入命令参数、日志、报告或共享文档；不要输出配置文件内容。
- 入口：在仓库根目录执行 `KB_ENV_FILE=.env.<env> node .agents/skills/kuaibuddy-preprod/scripts/kb_e2e.js login`。登录返回包含账号信息，记录执行结果时只保留脱敏后的成功或失败信息。登录会访问目标服务，仅在任务需要登录时执行。
- **浏览器 UI 测试补充**：若获授权通过浏览器登录 KuaiBuddy，登录后可能弹出「用户引导」浮层，需先点击「跳过」/「我知道了」/「关闭」关掉引导页，再操作页面元素。
- 令牌缓存保存在 `.runtime/cache/kuaibuddy-preprod/token.json`，匹配环境（`url`）、公司及账号后复用；切换环境或身份时重新登录（`login --force`）。缓存和配置均为本机敏感数据，不提交 Git。

## 任务执行

- 明确用户授权的测试范围、环境和数据；先检索已有资产，按 AGENTS.md 建立独立 Run。将业务操作和测试产物限定在授权范围内。
- `ask` 发起对话，`batch` 执行 JSONL，`sessions`、`messages` 回读会话，`agents`、`skills` 查询可用配置。运行 `node .agents/skills/kuaibuddy-preprod/scripts/kb_e2e.js --help` 查看参数。
- 对话请求会创建或更新远程会话并可能调用工具、消耗配额；只执行用户授权的测试。多轮逐轮等待完成并确认上下文，注意共享账号会话隔离。
- `ask`/`batch` 使用 `--out` 指向当前 Run 的 `artifacts/` 下独立目录，原始消息、事件和日志可能包含敏感信息，按需脱敏及归档。
- `ask` 与 `batch` 的单轮结果包含实际 `startedAt`、`finishedAt`（UTC）和耗时；保存到 Run 后按需用于记录。浏览器操作需单独记录真实起止时间，不能将进程退出码等同业务通过。
- 辅助列表接口返回非成功业务码时脚本报错并返回非零退出码；它只代表该接口失败，不足以认定默认助手或对话不可用。若已获对话授权且默认助手的使用范围清晰，可独立验证对话。
- 按正式需求与实际观察判断，区分执行成功和业务验证通过；记录未执行、阻塞及证据缺口。无授权或缺少依据时不擅自操作或编造结果。

## 排查

登录失败时检查环境配置、公司 ID 和账号状态，不输出密码；环境协议可能变化，不能把旧实现当作当前服务兼容性的保证。登录态失效可在确认环境和账号后强制登录；网络失败或权限错误应报告原因，避免反复尝试。
