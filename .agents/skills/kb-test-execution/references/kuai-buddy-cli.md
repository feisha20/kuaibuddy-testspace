# KuaiBuddy 多环境对话 CLI

需要 Node.js 18 及以上，使用 Node.js 内置模块。命令示例从仓库根目录运行。

| 目标环境 | 本机配置 |
| --- | --- |
| 测试 | `KB_ENV_FILE=.env.test` |
| 预生产 | `KB_ENV_FILE=.env.preprod` |
| 生产 | `KB_ENV_FILE=.env.prod` |

每次调用都显式提供对应的 `KB_ENV_FILE`。配置文件使用 `url`、`companyid`、`usrname`、`password`，与本次授权的站点及账号核对后再使用。没有指定配置文件时，也可以通过进程环境完整提供 `KB_URL`、`KB_COMPANY_ID`、`KB_USERNAME`、`KB_PASSWORD`。该方式也支持用 `--url` 显式覆盖地址。两种配置方式互斥；配置缺失或方式冲突时，脚本在请求发出前退出。通过本机可信配置加载器注入凭据，避免把真实值写入命令、日志或报告。

```bash
node .agents/skills/kb-test-execution/scripts/kb_e2e.js --help
KB_ENV_FILE=.env.test node .agents/skills/kb-test-execution/scripts/kb_e2e.js login
```

- `login` 仅在任务需要时执行。输出含账号信息，运行记录仅保留脱敏结论。令牌沿用 `.runtime/cache/kuaibuddy-preprod/token.json`，有效期内仅复用站点、公司和账号均匹配的令牌。需要刷新时使用 `login --force`。
- `ask` 发起一轮对话，使用 `--session <sessionId>` 可继续同环境同账号的已有会话。`batch` 串行读取 JSONL，适用于相互独立的批量用例。依赖上一轮输出的用例逐轮执行，检查终态后再继续。使用 `--out` 将产物放入当前 Run 的 `artifacts/` 下独立目录，记录实际 UTC 起止时间、会话 ID 和 runId。
- `sessions`、`messages` 回读会话，`agents`、`skills` 查询可用配置。辅助列表接口的业务失败按该接口记录，默认助手和对话能力依据各自的证据判断。已知环境观察见 [K-004](../../../../docs/knowledge.md#k-004预生产与测试环境-agents-列表接口返回业务码-9001-不代表对话不可用)。
- 生产会话读取与发起对话分别按用户授权执行。`ask`、`batch` 会创建或更新会话，可能调用工具、消耗配额。会话正文、SSE 事件和本地输出按敏感证据管理，分享前脱敏。
- 登录或请求失败时核对环境和身份。涉及会话写入且结果不明时，先查已有会话或运行证据，再决定是否重试。
