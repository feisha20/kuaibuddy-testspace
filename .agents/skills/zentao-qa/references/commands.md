# 配置与命令

所有示例在 Skill 目录运行，Agent应将脚本位置替换为实际绝对路径。无需 pip 安装；要求 Python 3.9+，macOS 使用 `python3`。

## 本机认证

复制 `config.example.json` 到 `.local/config.json`，填入本机账号密码即可长期使用，token可留空。也可通过终端交互登录并保存密码（输入时不显示）：

```sh
python3 scripts/zentao_qa.py --url http://pm.kuaishang.cn/zentao/ --account linjt --no-proxy login --save-password
python3 scripts/zentao_qa.py doctor
```

非交互调用使用 `ZENTAO_PASSWORD` 环境变量，或 `login --password-env 自定义变量名`。不要把真实密码放进命令参数、shell历史或可提交文件。密码以明文保存在本机配置中，文件权限0600，整个`.local/`目录受Git忽略规则保护。手工复制配置时也应将权限设为0600。

不希望持久化密码时，首次登录省略 `--save-password`，仅保存Token；已保存密码的同一账号重新登录会保留并更新密码。需要取消密码保存，可从本机配置删除password字段。

支持 `ZENTAO_URL`、`ZENTAO_ACCOUNT`、`ZENTAO_PASSWORD`、`ZENTAO_TOKEN`。`--url/--account` 优先于环境变量，环境变量优先于本地配置。显式设置环境Token时不使用配置密码续期，避免切换身份；只设置环境密码时可自动登录，但不会擅自将该密码持久化。改变站点或账号时不能沿用原配置凭据，需要重新登录或提供匹配的环境凭据。账号标识用于隔离本地账本，不是服务端身份校验。配置通过 `--config 路径` 或默认 `.local/config.json` 读取。

公司站点当前仅HTTP可达；`--no-proxy`只影响此工具请求，不改系统代理。默认遵循环境代理。

配置账号密码后，无Token时先自动登录；查询遇到HTTP401时自动重新登录并重试一次，新Token更新到同一账号的本机配置。403、网络故障、普通业务错误不重登；密码错误不会循环尝试。离线plan和未加commit的apply仍完全离线。

写请求发送前会进行只读预检，通常在此阶段完成续期；如果写请求本身遇到401，工具刷新Token后停止本次写入，不自动重发，账本保留不确定状态。配置变更时也不会覆盖其他账号的凭据。

## 只读操作

```sh
python3 scripts/zentao_qa.py read products --all
python3 scripts/zentao_qa.py read projects --all
python3 scripts/zentao_qa.py read executions --scope project --scope-id 750 --all
python3 scripts/zentao_qa.py read stories --scope execution --scope-id 697 --all
python3 scripts/zentao_qa.py read story --id 123
python3 scripts/zentao_qa.py read context --id 123
python3 scripts/zentao_qa.py read cases --scope product --scope-id 1 --story-id 123
python3 scripts/zentao_qa.py read case --id 789
python3 scripts/zentao_qa.py read bugs --scope execution --scope-id 697 --all
python3 scripts/zentao_qa.py read bug --id 100
python3 scripts/zentao_qa.py read builds --scope execution --scope-id 697 --all
python3 scripts/zentao_qa.py read testtasks --scope execution --scope-id 697 --all
python3 scripts/zentao_qa.py read testtask --id 456
python3 scripts/zentao_qa.py read results --id 789
python3 scripts/zentao_qa.py read task --id 100
python3 scripts/zentao_qa.py read tasks --scope execution --scope-id 697 --all
python3 scripts/zentao_qa.py read users --kw 黄景霖
python3 scripts/zentao_qa.py read user --id 8
```

示例编号仅表示参数格式，使用前查询实际编号，不要直接据此创建对象。

### 姓名与登录账号

指派Bug、任务时只能填禅道登录账号（如 `hjl`），不能填中文姓名；`assignedTo`/`responsible` 含非ASCII字符会在离线 `plan` 阶段被拒绝并提示查询账号。用 `read users --kw 关键字` 把姓名换成账号：

```bash
python3 scripts/zentao_qa.py read users --kw 黄景霖        # 按姓名
python3 scripts/zentao_qa.py read users --kw hjl           # 按账号
python3 scripts/zentao_qa.py read users --kw huangjinglin  # 按拼音
python3 scripts/zentao_qa.py read users --kw hjl --exact   # 账号/姓名/拼音分词完全一致
```

`--kw` 会读取全部分页后本地过滤（22.2 的 `/users` 忽略服务端关键字参数），结果只含 `id`、`account`、`realname`、`pinyin`、`role`、`dept`，不带登录IP等无关信息。同名或近似匹配可能返回多条（如“黄川峰”对应 `hcf`、`huangcf`），必须把候选列给用户确认后再写入，不能自行挑一个。`read user --id` 读取单个用户。

`context` 组合需求详情、产品下按需求过滤后的全部用例及Bug；附件不下载。单页查询 `complete=false`，`--all` 从第1页取完后 `complete=true`。部分详情无权限时整体失败，不伪装成“没有相关记录”。

## 写入计划

计划为JSON对象，顶层只含 `schemaVersion: 1` 和 `operations`，每批1至100项。

操作通用字段：`key`、`action`、`data`；可选 `expected`；`bug.update`、`case.review`、`task.start` 接受 `targetId`。`case.create` 可选 `autoReview`（布尔值，默认true）。

```json
{
  "schemaVersion": 1,
  "operations": [
    {
      "key": "story-123-v2-invalid-phone",
      "action": "case.create",
      "expected": {"storyVersion": 2},
      "data": {
        "productID": 1,
        "story": 123,
        "project": 2,
        "execution": 3,
        "title": "手机号不足11位时拒绝提交",
        "type": "feature",
        "pri": 2,
        "precondition": "已进入注册页面，其他必填项均有效",
        "steps": ["输入10位手机号并提交"],
        "expects": ["提示手机号格式不正确，不创建账号"]
      }
    }
  ]
}
```

本地保存到 `private/plan.json` 等忽略目录。下面前两条完全离线，不登录、不联网、不写账本：

```sh
python3 scripts/zentao_qa.py plan --file private/plan.json
python3 scripts/zentao_qa.py apply --file private/plan.json
python3 scripts/zentao_qa.py apply --file private/plan.json --commit
```

`--commit`是工具执行开关，不能替代用户授权。按用户指令自主完成已授权写入。每项提交前检查、提交后回读，首个失败停止后续写入。

新增用例默认自动评审通过：创建结果为wait时执行正式评审；已为normal时不重复评审。创建和评审独立记账，评审失败时返回已创建的remoteId，不会在重跑时重复创建。用户明确要求保留待评审时，才在case.create操作顶层添加 `"autoReview": false`。自动评审使用当前配置账号作为评审人，工具显式传入Asia/Shanghai当前日期，再由禅道保存。

### 操作字段

| action | 必填data字段 | 可选data字段 |
|---|---|---|
| `case.create` | productID、title、steps、expects | module、story、pri、type、precondition、stepType、project、execution |
| `case.update` | targetId 和 expected.caseVersion/storyId/lastEditedDate | title、precondition、pri、type、steps、expects（步骤和预期须同时提供） |
| `task.update` | targetId 和 expected.storyId/lastEditedDate | name、assignedTo、desc、pri、estimate、estStarted、deadline |
| `case.review` | result（仅pass）、reviewedBy（单个账号组成的数组） | reviewedDate（YYYY-MM-DD）、comment |
| `bug.create` | productID、title、openedBuild、steps | project、execution、severity、pri、type、story、assignedTo、bugLabel、responsible |
| `bug.attach` | path、filename、sha256、size | 无 |
| `bug.update` | 至少一个待修改字段 | title、severity、pri、type、openedBuild、steps、project、execution、story、assignedTo、bugLabel、responsible |
| `task.create` | name、executionID | parent、type（仅test）、assignedTo、estStarted、deadline、pri、estimate、module、story、desc |
| `task.start` | left、consumed、assignedTo | realStarted、comment |
| `task.finish` | targetId、expected.storyId/lastEditedDate；data.currentConsumed、consumed、assignedTo、realStarted | comment |
| `testtask.create` | productID、name、build、begin、end | execution、type、owner、status、desc |
| `testtask.linkcase` | caseId、caseVersion、testtaskId | 无 |
| `result.report` | caseId、caseVersion、testtaskId、result（fail/blocked）、report | 无 |
| `result.submit` | caseId、caseVersion、testtaskId、steps、result、evidence；真实执行另需startedAt、finishedAt | simulation（默认false） |

凡data含非零 `story`，必须同时给 `expected.storyVersion`。修改Bug另需 `targetId` 和 `expected.lastEditedDate`，该值原样取自详情接口，未编辑过的Bug返回空值时使用空字符串，仍需预检匹配。

已有用例评审使用 `case.review`，另需targetId和expected中的caseVersion、storyId、lastEditedDate。storyId=0表示无关联需求；未编辑的新用例lastEditedDate可为空字符串。示例操作：

```json
{
  "schemaVersion": 1,
  "operations": [{
    "key": "review-case-789-v1-pass",
    "action": "case.review",
    "targetId": 789,
    "expected": {"caseVersion": 1, "storyId": 123, "lastEditedDate": ""},
    "data": {"result": "pass", "reviewedBy": ["你的实际评审账号"], "comment": "用例评审通过"}
  }]
}
```

工具要求待评审状态，正式提交后核对normal状态、评审人和评审日期；不会新增用例执行结果。请使用有评审权限的实际账号，不通过直接修改status代替评审。

22.2实机要求显式提供合法日期；工具在reviewedDate省略时自动填入Asia/Shanghai当前日期。不能把完整时间戳作为reviewedDate。

用例 `steps/expects` 是对应的字符串数组，仅支持平铺步骤；`stepType`省略时自动填step。`openedBuild`为数组，如 `[10884]`，主干为 `["trunk"]`；测试单 `build` 则必须是数字构建ID。日期为YYYY-MM-DD；测试单的需求范围写在desc中，禅道没有在此接口提供原生story参数。

测试单创建后手动关联用例，再读取测试单确认。MVP不支持同一批通过前一步返回ID自动引用下一步；先提交创建，得到ID后再生成后续计划。

测试主子任务使用task.create：先创建不关联单一需求的冲刺主任务，拿到ID后，创建带 `parent=主任务ID` 和 `story=需求ID` 的子任务。parent省略或为0表示顶层任务。工具核对父任务属于同一冲刺、类型为test、尚未完成/取消/关闭，写入后核对子任务parent和父任务isParent标记。需要需求版本锁时按上述expected.storyVersion要求填写；不要虚构预计工时或截止日期。

启动测试任务使用task.start，需要targetId及expected.storyId/lastEditedDate（未修改时空字符串）。left为用户确认的预计剩余工时，至少0.01小时；consumed必须原样采用刚读取的现有总消耗，assignedTo采用原负责人。工具在realStarted省略时按Asia/Shanghai填入实际开始时间，格式YYYY-MM-DD HH:MM:SS。仅支持启动未开始的叶子测试任务，子任务启动后回读父任务联动。该动作不执行用例，也不写测试结果；不能将剩余0小时提交给start，否则禅道会直接完成任务。

### 执行结果示例

```json
{
  "schemaVersion": 1,
  "operations": [{
    "key": "batch-20261019-01-case-789-attempt-1",
    "action": "result.submit",
    "data": {
      "caseId": 789,
      "caseVersion": 2,
      "testtaskId": 456,
      "result": "fail",
      "startedAt": "2026-10-19T10:00:00+08:00",
      "finishedAt": "2026-10-19T10:00:12+08:00",
      "evidence": ["artifacts/batch-20261019-01/request-response.json"],
      "steps": [{"stepId": 1001, "result": "fail", "actual": "提交后返回500，未显示校验提示"}]
    }
  }]
}
```

从 `read case` 获取步骤ID，严格按服务器步骤顺序提供全部步骤。整体结果按 fail优先、blocked其次、否则pass判断。测试单需已关联该版本；MVP不写历史版本或分组步骤。

evidence是证据引用/说明，不会上传附件，也不会自动验证证据真假；真实执行时调用Agent负责确认实际结果和文件存在。原始时间、证据和操作key写入各步骤的实际结果，禅道执行人和执行日期仍由服务端生成。

### 逐步模拟调试

仅在用户明确授权模拟数据时设置data.simulation=true，steps仍逐步提供stepId/result/actual。此时禁止填写startedAt/finishedAt，避免虚构真实执行时间；evidence说明用户授权及调试用途。工具在每步实际情况自动追加“调试模拟，非真实产品测试结果”及稳定key。没有该标志时仍必须填写真实起止时间。

真实执行和模拟调试都按步骤填写：已确认通过使用pass，具体不符合预期使用fail，因前置异常不能继续验证使用blocked，实际情况解释原因。模拟场景必须在说明中明确标注，不能推广为真实测试结果。

### 追加关联与整体结果报告

两者均要求expected.storyId，核对用例当前版本、正常状态、产品及冲刺、测试单未结束。先提交关联计划并回读，再提交结果计划；整批预检不会假设前项尚未提交的关联已经存在。

```json
{
  "schemaVersion": 1,
  "operations": [{
    "key": "round-456-link-case-789-v2",
    "action": "testtask.linkcase",
    "expected": {"storyId": 123},
    "data": {"caseId": 789, "caseVersion": 2, "testtaskId": 456}
  }]
}
```

已有同版本关联直接回读，不调用服务端replace；不同版本或重复执行条目停止，不覆盖已有执行记录。关联本身不写执行结果。

用户明确报告整例失败/阻塞，但没有逐步结果时使用如下独立计划。report说明来源及已知现象，不能据整体失败推断每步失败；步骤结果留空。禅道22.2执行历史页面在步骤result为空时也隐藏real，因此result.report仅表示整体结果及接口可读说明已存储，不能用于要求逐步显示测试结果/实际情况的场景。需要填写这两列时使用result.submit。用户明确授权构造调试数据时使用simulation=true的逐步提交；旧report调试记录仍保留。仅模拟结果不能用于验收或自动生成真实Bug。

```json
{
  "schemaVersion": 1,
  "operations": [{
    "key": "round-456-case-789-report-1",
    "action": "result.report",
    "expected": {"storyId": 123},
    "data": {
      "caseId": 789, "caseVersion": 2, "testtaskId": 456,
      "result": "fail",
      "report": "用户报告：取消授权后刷新，目标账户仍显示有效授权；具体步骤结果及原始执行时间未提供。"
    }
  }]
}
```

该操作只传入一条用例，通过22.2动态batchRun动作独立写入整体结果；不更改其他用例，不修改工作任务工时。服务端记录当前账号及提交时刻，来源说明和稳定操作key随实际结果保存。回读核对唯一结果记录、执行条目、用例版本、整体结果及步骤留空状态。逐步执行仍使用result.submit。

## 防重、错误与恢复

账本位于配置同目录 `journal.sqlite3`，可用 `apply --journal 路径`指定共享账本。Codex和ZCode在同一本地工作区应共用配置和账本。

- `already_applied`：同key同内容已成功，跳过写入。
- `KEY_CONFLICT`：同key内容变了，停止。新业务动作使用新key。
- `CONFLICT`：需求版本或Bug修改时间变化，重读后重新设计。
- `CASE_NOT_LINKED`：测试单未关联用例或版本不同，先在禅道处理。
- `VERIFY_FAILED`：服务端已提交但回读未通过；同计划重跑只回读，不重发。
- `UNCERTAIN_WRITE`：超时、异常响应或中断后可能已写入，禁止重发；先核查，不能删除账本“修复”。工具不会自动解除该状态。
- `BUSY`：另一进程正在写同一账本，待其结束再运行。
- `AUTH_REFRESHED_WRITE_STOPPED`：写请求遇到认证失效，已重新登录但未重发；先核查远端，再处理不确定账本状态。
- `CONFIG_CONFLICT`：自动登录期间本机配置已被修改，未覆盖配置；核对当前账号后重新运行。
- `BUSINESS_ERROR`：禅道业务拒绝，正文不回显，避免泄露敏感信息。检查实际字段和账号权限；发生在写入时按不确定状态处理。
- `AUTH_FAILED/PERMISSION_DENIED/NOT_FOUND/NETWORK_ERROR` 分别处理，不解释成空清单。

本地账本不是跨机器全局防重；换机器/删除账本/换key可能重复创建。跨机器重做前先查远端。执行结果的 `[zentao-qa:key]` 标记可辅助核查；创建用例和Bug不修改标题插入技术标记。

### 被拒绝的评审核查

`read review --id 用例ID` 从用例详情只读查询评审状态、评审人、日期及Reviewed历史；失败时返回脱敏业务原因。已评审的用例不能再进入review表单，因此历史查询使用详情接口。

对于明确被拒绝的已有用例评审，可运行：

```sh
python3 scripts/zentao_qa.py reconcile-review --file private/review-plan.json --key review-case-789-v1-pass
```

该命令只适用于case.review的pending/uncertain账本。它核对原计划哈希、待评审状态、用例版本、关联需求和修改时间，且要求评审字段为空、没有Reviewed历史；满足后记录只读核查证据并将本地状态改为not_applied。它不执行评审，也不适用于用例创建、执行结果或Bug等其他写入。修正明确原因后，再显式提交原计划。

### 提交响应异常但执行记录已保存

22.2实机存在POST v1/testcases/{id}/results保存结果后返回非JSON的情况。禁止按响应错误直接重发。先read results查看唯一操作key，核对版本、run、每步结果和actual。随后可运行：

```bash
python3 scripts/zentao_qa.py reconcile-result --file 原始计划.json --key 原始操作key
```

该命令只读远端并将本地pending/uncertain转为verified；不会发业务写请求，也不会恢复为可提交。仅支持result.submit，原计划内容必须与账本哈希相同；记录不存在、多条匹配、版本/执行条目/内容不符时停止，保留原状态。submitted回读失败仍用原apply计划只回读即可。

Bug创建或修改可通过assignedTo指定账号（例如用户明确要求指派给自己时，采用doctor确认的当前account，不使用显示姓名）。提交后回读核对负责人账号。调试Bug在标题和实际结果中保留简短“【调试模拟】”标记，按用户授权登记并关联需求；用例、测试单及执行记录编号保存在本机计划/记录中，不自动堆入详情。

`bug.update` 是部分字段更新，但22.2对未提交的 `pri`/`severity`/`type` 按编辑表单默认值落库（3、3、codeerror）。工具在提交前读取当前Bug，把计划里没写的这三个字段按原值显式带回，并在回读时逐项核对；计划里显式给出的值优先。因此移动冲刺、改标题、改指派人等局部更新不会再把优先级静默打回3。已用该实例验证：原pri=1的Bug移动执行后仍为1，回读不一致时报VERIFY_FAILED。

公司自定义字段：bugLabel为非空字符串数组，responsible为问题责任人账号。是否必填及标签值取决于实例，不把当前公司的要求推广到其他站点。先读取现有记录核实字段值；此实例已观察到other/reproduce/cusRepeated，不能凭名称臆造新值。普通GET创建表单可读取基础上下文，但不会完整返回自定义枚举：

```bash
python3 scripts/zentao_qa.py read bugform --scope product --scope-id 产品ID
```

Bug重现步骤回读允许编辑器移除相邻块元素间的格式换行；正文、段内空格和内联标签仍需一致。出现VERIFY_FAILED时用原计划仅回读，不重复创建。业务必填校验拒绝后也先核查远端，确认未创建并保留拒绝/查询证据；内容补齐使用新key，禁止删除原账本绕过不确定状态。

### Bug描述遵循实例模板

创建前读取read bugform，取返回data.bug.steps作为当前默认重现步骤模板。API提交steps是整段正文，不会自动套入网页编辑器模板，Agent必须在生成计划时保留模板栏目和顺序，将内容填入各栏。当前实例为[步骤]、[结果]、[期望]，使用如下结构：

```html
<p>[步骤]</p>
<ol><li>进入目标页面。</li><li>选择符合初始状态的对象并执行操作。</li><li>刷新或查询，检查操作后的状态。</li></ol>
<p>[结果]</p>
<p>观察到的异常现象；模拟数据只加简短“【调试模拟】”标记。</p>
<p>[期望]</p>
<p>应满足的行为和验收结果。</p>
```

标题、指派人和其他字段独立填写，不需要为了套模板修改。用户另行指定的模板优先；read bugform只提供当前默认正文，无法枚举编辑器“应用模板”中个人保存的命名模板，不能冒称已读取。修复已有Bug模板时，先读最新lastEditedDate，再用bug.update仅提交steps，保留原有事实及简短模拟标识。标题仅填title，详情不重复；步骤仅写操作，不单列前置条件、Skill调试说明或追溯清单。必要初始状态融入具体操作，结果与期望分别只写现象与应有行为。

### Bug截图上传及插入正文

仅按用户指定文件和目标Bug上传。bug.attach使用targetId及expected.storyId，data.path为本地绝对路径；filename为安全英文文件名（最长120字符、以字母或数字开头，只含字母/数字/点/下划线/连字符），当前仅支持PNG、最大10MiB。sha256为源文件十六进制SHA256，size为字节数；计划校验及真正发送前均检查文件没有变化。

```json
{
  "schemaVersion": 1,
  "operations": [{
    "key": "bug-123-attach-screenshot-1",
    "action": "bug.attach",
    "targetId": 123,
    "expected": {"storyId": 456},
    "data": {
      "path": "/绝对路径/截图.png",
      "filename": "bug-123-screenshot.png",
      "sha256": "使用源文件实际SHA256替换此值",
      "size": 12345
    }
  }]
}
```

通过POST v2/files发送multipart/form-data，字段file为文件二进制，objectType=bug、objectID=目标Bug。不把本地路径当文件内容发送，也不使用JSON上传。回读Bug.files核对文件ID、objectType/objectID及文件大小；上传响应url仅保留为uploadUrl，不能直接用作正文地址。回读附件webPath后，以不附带Token、不跟随重定向的GET读取同站点data/upload路径，检查PNG文件头、字节大小及SHA256与源文件一致。服务端未返回Content-Type时仍检查文件头，HTTP200返回HTML不视为成功。验证后的remote.url才用于正文；remote.imageReadable=true。重跑同key不重复上传。

若用户要求正文显示：先运行 `read bugimage --id 文件ID --scope-id BugID`，它从目标Bug附件元数据核验webPath并返回可读PNG的url及哈希。对旧版已上传文件同样执行该核验，不直接复用旧账本的url。之后独立读取Bug详情，将bugimage返回的url经HTML属性转义后置于 `<img src="已验证的图片URL" alt="截图" />`，插在[结果]栏目现象之后，再以最新lastEditedDate执行bug.update。只要求附件时无需修改正文。正文更新失败不重新上传；上传响应异常时停止并读Bug附件列表核查，禁止自动换key重传或删除账本。reconcile-result不适用于上传。

实机验证区分附件保存、正文引用保存与浏览器显示；未经用户要求不启动浏览器。

正文图片故障排查：附件已显示不代表正文URL可显示图片。只读比较正文引用与附件元数据中的webPath；通过read bugimage核验PNG字节，再用最新lastEditedDate更新img.src。不得通过改扩展名、凭空拼data/upload路径、重新上传或把Token放入URL来解决。该命令不落盘图片，只返回字节大小、SHA256及URL。远端字节可读与浏览器渲染验收分别报告。

### 编辑测试任务与用例

以下操作沿用 `plan`、`apply --commit` 和现有防重账本，写入需明确授权。先读取目标最新详情，`case.update` 同时核对版本、需求和修改时间；`task.update` 核对需求和修改时间。未编辑时 `lastEditedDate` 使用空字符串。任务仅支持测试类型，指派必须为禅道登录账号；任务执行状态与工时由相应动作管理。

```json
{"schemaVersion":1,"operations":[
  {"key":"task-12-rename-20261105","action":"task.update","targetId":12,"expected":{"storyId":0,"lastEditedDate":""},"data":{"name":"【单轮对话】预生产回归","assignedTo":"account"}},
  {"key":"case-11-rename-20261105","action":"case.update","targetId":11,"expected":{"caseVersion":1,"storyId":0,"lastEditedDate":""},"data":{"title":"【单轮对话】发送消息"}}
]}
```

用例编辑仅支持平铺步骤，需先读齐原字段和所有步骤；工具带回步骤、预期与 `stepType`，回读核对字段和步骤内容。修改步骤时一次提供 `steps` 和 `expects` 数组，可能影响版本与已有测试单的版本关联：编辑前先检查历史并与工程师确认，编辑后检查关联和历史，不自动重建测试单或执行结果。任务更新回读验证状态、已消耗和剩余工时未变；发生不一致停止并报告。`VERIFY_FAILED` 表示可能已写入，只对原计划回读，不能重复发送。此能力通过模拟测试，真实禅道 22.2 写入兼容性和对已有执行历史的影响仍需验证。

### 完成测试工作任务

先读取目标任务：仅进行中的叶子测试任务可完成。`data.consumed` 是读取到的已有累计消耗，`currentConsumed` 是用户确认的本次实际消耗；`assignedTo` 和 `realStarted` 原样取任务当前值。工具向禅道提交累计消耗，完成时间取实际操作时间，回读核对状态、总工时、剩余工时和父任务状态。禁止倒填或虚构执行时间；父任务可能由禅道自动联动完成。

```json
{"schemaVersion":1,"operations":[{"key":"task-12-finish-1h","action":"task.finish","targetId":12,"expected":{"storyId":0,"lastEditedDate":"2026-11-05 16:46:43"},"data":{"currentConsumed":1,"consumed":0,"assignedTo":"account","realStarted":"2026-11-05 16:46:43"}}]}
```

遵守防重账本；写入响应不确定时先回读核查，禁止重发或删除账本。
