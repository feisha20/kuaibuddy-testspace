---
name: kuaibuddy-preprod
description: 在 KuaiBuddy 预生产环境登录、执行获授权的对话测试或回读会话时使用，使用项目本地配置和运行目录。
---

# KuaiBuddy 预生产登录与对话测试

读取仓库 AGENTS.md、README.md 和相关任务资产。此技能只用于用户指定的预生产任务，不将配置自动用于其他环境；不依赖浏览器。

## 登录与凭据

- 需要 Node.js 18 及以上，无第三方依赖。脚本 `scripts/kb_e2e.js` 默认只读取仓库根目录 `.env.preprod`；也可通过 `KB_ENV_FILE` 显式指定配置文件，或通过 `KB_URL`、`KB_COMPANY_ID`、`KB_USERNAME`、`KB_PASSWORD` 覆盖对应项。不得回退读取其他项目的配置。
- `.env.preprod` 字段为 `url`、`companyid`、`usrname`、`password`。密码、令牌和账号不写入命令参数、日志、报告或共享文档；不要输出配置文件内容。
- 入口：在仓库根目录执行 `node .agents/skills/kuaibuddy-preprod/scripts/kb_e2e.js login`。登录返回包含账号信息，记录执行结果时只保留脱敏后的成功或失败信息。登录会访问目标服务，仅在任务需要登录时执行。
- 令牌缓存保存在 `.runtime/cache/kuaibuddy-preprod/token.json`，匹配环境、公司及账号后复用；切换身份时重新登录。`login --force` 强制重新登录。缓存和配置均为本机敏感数据，不提交 Git。

## 任务执行

- 明确用户授权的测试范围、环境和数据；先检索已有资产，按 AGENTS.md 建立独立 Run。将业务操作和测试产物限定在授权范围内。
- `ask` 发起对话，`batch` 执行 JSONL，`sessions`、`messages` 回读会话，`agents`、`skills` 查询可用配置。运行 `node .agents/skills/kuaibuddy-preprod/scripts/kb_e2e.js --help` 查看参数。
- 对话请求会创建或更新远程会话并可能调用工具、消耗配额；只执行用户授权的测试。多轮逐轮等待完成并确认上下文，注意共享账号会话隔离。
- `ask`/`batch` 使用 `--out` 指向当前 Run 的 `artifacts/` 下独立目录，原始消息、事件和日志可能包含敏感信息，按需脱敏及归档。
- 按正式需求与实际观察判断，区分执行成功和业务验证通过；记录未执行、阻塞及证据缺口。无授权或缺少依据时不擅自操作或编造结果。

## 排查

登录失败时检查环境配置、公司 ID 和账号状态，不输出密码；环境协议可能变化，不能把旧实现当作当前服务兼容性的保证。登录态失效可在确认环境和账号后强制登录；网络失败或权限错误应报告原因，避免反复尝试。
