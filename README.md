# tdaypay-integration 使用说明

`tdaypay-integration` 是一个面向 Codex 的 TDayPay 集成 Skill。它会先识别现有项目的技术栈、代码风格和业务流程，提出集成方案并等待确认，然后按照项目原有约定实现代收、出款、余额查询、订单状态查询和回调处理。

本文档面向 Skill 使用者。行为和安全边界的最终依据是 Skill 目录中的 `SKILL.md`、`references/` 和 `scripts/`。

## 1. 主要作用

这个 Skill 主要解决以下问题：

1. **适配现有项目**：识别语言、框架、包管理器、HTTP 客户端、配置方式、校验库、日志和测试框架，避免生成与项目风格脱节的通用代码。
2. **确认集成方式**：编码前明确业务动作、国家币种、支付渠道、同步响应、异步状态、幂等责任和持久化边界。
3. **生成 TDayPay 集成代码**：支持 `payment`、`payout`、`balance`、`query` 和 callback。
4. **执行国家与渠道校验**：将公共规则、国家规则和渠道规则合并，阻止缺少必填字段、非法枚举、错误账户格式和金额规则冲突。
5. **生成强制规则注释**：在校验代码旁生成带来源与核验日期的 `TDAYPAY-RULE[...] [REQUIRED]` 注释。
6. **保证签名一致性**：确保签名使用的 UTF-8 JSON 与实际发送的 JSON 完全一致。
7. **实现安全回调**：验证原始请求体签名、处理重复通知、保存状态历史，并支持 `SUCCESS -> REVERSED`、`FAILED -> SUCCESS` 等状态变化。
8. **控制生产风险**：集成设计确认只允许开始编码，不代表允许发送生产交易；生产发送必须获得当前请求中的明确授权。

## 2. 支持范围

| 能力 | TDayPay method | 说明 |
|---|---|---|
| 代收 | `pay` | 创建支付订单，处理收银台地址和异步支付状态 |
| 出款 | `payOut` | 创建出款订单，验证收款人、账户和渠道规则 |
| 余额查询 | `balance` | 查询指定币种余额 |
| 订单查询 | `verifyStatus` | 使用 TDayPay 平台订单号查询状态，单次最多 200 个 |
| 回调接收 | — | 验签、字段校验、幂等处理、状态历史和安全应答 |

当前规则目录对墨西哥 `MXN` 和哥伦比亚 `COP` 提供较详细的渠道校验；其他币种可能只有网关路由信息。渠道是否对某个商户实际开通，仍以当前商户合同和 TDayPay 配置为准。

## 3. 不支持的范围

除非用户明确扩大任务范围，本 Skill 不负责：

- OMS 后台管理；
- 2FA 绑定；
- 商户对账；
- 任意退款操作；
- 根据国家支付网络能力推断当前商户已经开通某个 TDayPay 渠道；
- 在没有当前生产发送授权的情况下创建真实交易。

## 4. 目录结构

```text
tdaypay-integration/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── api-contract.md
│   ├── callback-validation.md
│   ├── country-catalog.md
│   ├── fields.md
│   ├── integration-eval-cases.md
│   ├── integration-guidance.md
│   ├── payment-network-rules.md
│   ├── eval-cases.json
│   └── rules.json
└── scripts/
    ├── inspect_project.py
    ├── country_rules.py
    ├── rule_comment_plan.py
    ├── tdaypay_callback.py
    ├── tdaypay_request.py
    └── integration_selftest.py
```

关键文件说明：

- `SKILL.md`：Skill 工作流程和安全边界。
- `references/rules.json`：机器可读的国家、币种和渠道规则。
- `references/country-catalog.md`：面向人的国家和渠道说明。
- `references/callback-validation.md`：回调验签、幂等和状态处理要求。
- `scripts/country_rules.py`：国家和渠道规则查询、解释及校验工具。
- `scripts/rule_comment_plan.py`：强制校验注释生成器。
- `scripts/tdaypay_callback.py`：离线回调验签和回调注释生成器。
- `scripts/tdaypay_request.py`：请求准备、签名和显式生产发送参考工具。

## 5. 安装

### 5.1 从 ZIP 安装

准备目标目录，并把压缩包内容解压到 Skill 目录：

```bash
mkdir -p ~/.codex/skills/tdaypay-integration
unzip tdaypay-integration.zip -d ~/.codex/skills/tdaypay-integration
```

解压后应满足：

```text
~/.codex/skills/tdaypay-integration/SKILL.md
```

不要形成重复目录，例如：

```text
~/.codex/skills/tdaypay-integration/tdaypay-integration/SKILL.md
```

安装完成后，新建一个 Codex 任务或重新加载 Skill 列表。

### 5.2 运行要求

- Python 3.10 或更高版本；
- Python 标准库，无额外运行时依赖；
- 可访问需要集成的项目目录；
- 仅在准备或发送签名请求时需要 TDayPay 商户凭据。

## 6. 凭据配置

辅助请求脚本从环境变量读取凭据：

```bash
export TDAYPAY_MCH_ID='your-merchant-id'
export TDAYPAY_MERCHANT_KEY='your-merchant-key'
```

安全要求：

- 生产环境应通过现有 Secret Manager、密钥服务或受控环境变量注入凭据；
- 不要把凭据提交到代码仓库、测试夹具或日志；
- `merchantKey` 不支持通过命令行参数传入，避免进入 shell 历史；
- 输出和诊断中必须遮蔽商户凭据、签名、银行账号、身份号码、邮箱和手机号。

## 7. 推荐使用方式

### 7.1 第一步：让 Skill 检查项目

示例提示词：

```text
使用 tdaypay-integration 检查 /path/to/project，
为墨西哥 MXN SPEI 代收设计集成方案。先不要修改代码。
```

Skill 会检查：

- 项目语言、框架和包管理器；
- 已有 HTTP、配置、校验、日志和测试工具；
- 最接近的第三方支付模块；
- 订单、幂等、持久化和异步状态处理方式。

### 7.2 第二步：确认集成方案

Skill 会给出一个与项目匹配的方案，通常包括：

- 模块边界和接口；
- 请求签名及序列化责任；
- 国家规则校验责任；
- 回调、查询和状态历史；
- 需要修改的文件；
- 测试范围和未解决的业务问题。

用户确认方案后，Skill 才会开始修改目标项目。

示例：

```text
确认该集成方案，按照项目现有代码风格实现并运行测试。
```

### 7.3 第三步：检查实现结果

完成后应确认：

- 每个生成的 `[REQUIRED]` 规则都有对应代码；
- 签名测试证明签名 JSON 与发送 JSON 完全相同；
- 超时不会直接触发重复创建订单；
- 同步 `resultCode=000000` 没有被误认为最终支付成功；
- 回调验签、重复通知和可逆状态变化得到测试；
- 日志、错误和测试数据已经脱敏。

## 8. 常用调用示例

### 8.1 集成代收

```text
使用 tdaypay-integration，在这个 Spring Boot 项目中集成墨西哥 MXN SPEI 代收。
先检查现有 WebClient、配置、校验和测试风格，再给出方案让我确认。
```

### 8.2 集成出款

```text
使用 tdaypay-integration，在这个 NestJS 项目中集成哥伦比亚 COP NET_BANKING 出款。
沿用现有 Axios、class-validator、日志和 Jest，不要新增人工审核流程。
```

### 8.3 集成回调

```text
使用 tdaypay-integration，为现有 FastAPI 项目实现 TDayPay payment 和 payout 回调。
要求使用原始请求体验签、持久化去重、保留状态历史，并覆盖反转状态测试。
```

### 8.4 查询规则但不编码

```text
使用 tdaypay-integration，说明 COP PSE 代收需要哪些公共参数、渠道参数和强制校验。
不要修改代码，也不要发送交易。
```

### 8.5 准备交易但不发送

```text
使用 tdaypay-integration，根据已经确认的集成方案准备一笔测试请求，
只展示脱敏后的请求摘要和校验结果，不发送到生产。
```

## 9. 命令行辅助工具

以下命令应在 `tdaypay-integration` 目录中执行。

### 9.1 检查项目技术栈

```bash
python3 scripts/inspect_project.py --root /path/to/project
```

该命令只输出项目结构和依赖信号，不读取或输出密钥内容。

### 9.2 查看国家规则

```bash
python3 scripts/country_rules.py show --currency COP
```

### 9.3 解释国家和渠道规则

```bash
python3 scripts/country_rules.py explain payment \
  --currency COP \
  --payment-type PSE
```

输出会保留用户输入的 `PSE`，同时给出只适用于 COP 代收的规范化结果 `NET_BANKING`，并区分 TDayPay 规则和国家支付网络事实。

### 9.4 快速检查高风险字段

```bash
python3 scripts/country_rules.py check payment \
  --currency COP \
  --payment-type NET_BANKING \
  --amount 5000 \
  --bank-code 001
```

快速检查只校验已提供的高风险字段，不等同于完整请求校验。

### 9.5 校验完整请求体

```bash
python3 scripts/country_rules.py validate payment \
  --body-file payment.json
```

优先使用 `--body-file`，不要通过 `--body-json` 把敏感数据写入 shell 历史。

### 9.6 生成国家规则代码注释

```bash
python3 scripts/rule_comment_plan.py payment \
  --currency COP \
  --payment-type PSE \
  --language typescript \
  --format comments
```

支持根据语言生成 `#`、`//`、`--` 或其他对应形式的注释。

### 9.7 生成回调校验注释

```bash
python3 scripts/tdaypay_callback.py comments \
  --language typescript \
  --format comments
```

### 9.8 离线验证回调

```bash
TDAYPAY_MERCHANT_KEY='<secret>' \
python3 scripts/tdaypay_callback.py verify \
  --body-file callback.raw.json \
  --sign '<sign-header>' \
  --region latin \
  --source-ip 18.228.164.232
```

`callback.raw.json` 必须是服务实际收到的原始请求字节，不能先解析后重新序列化。

### 9.9 准备并签名请求，但不发送

```bash
python3 scripts/tdaypay_request.py payment \
  --body-file payment.json
```

默认模式为 `prepare-only`。它会生成网关、请求头、签名和校验警告，但不会进行网络请求。

### 9.10 生产发送

所有已记录的 TDayPay 网关都是生产网关。只有在当前用户请求已经明确授权生产发送时，才能执行：

```bash
python3 scripts/tdaypay_request.py payment \
  --body-file payment.json \
  --send \
  --confirm-live-send
```

确认集成方案、完成代码实现或之前发送过交易，都不能替代本次操作的生产发送授权。发生超时或结果不明确时，应先查询订单状态，不能直接重复创建订单。

## 10. 签名规则

### 10.1 出站请求签名

请求头固定包含：

```text
serviceName=api.pay
method=pay | payOut | balance | verifyStatus
mchId=<merchant-id>
signType=SHA512
timestamp=<Unix seconds>
Content-Type=application/json
```

签名原文没有分隔符：

```text
mchId + serviceName + method + timestamp + signType + exactJsonBody + merchantKey
```

使用 UTF-8 编码计算 SHA-512，并输出小写十六进制摘要。签名完成后不能再次格式化、重排字段或重新序列化 JSON。

### 10.2 回调签名

回调签名规则与出站签名不同：

```text
SHA512(exactRawCallbackBody + merchantKey)
```

验签必须发生在 JSON 解析之前，并使用恒定时间比较。

## 11. 回调处理要求

推荐处理顺序：

1. 捕获未解析的原始请求体；
2. 读取并验证 `sign` 请求头；
3. 验签通过后解析 UTF-8 JSON；
4. 校验必填字段、金额格式、订单类型和 UTC 时间；
5. 同时核对 `orderId` 与本地保存的 `mchOrderId`；
6. 持久化原始请求指纹和追加式状态事件；
7. 对相同事件去重，但保留同一订单的不同状态变化；
8. 幂等执行账务副作用；
9. 持久化成功后返回 HTTP 200、`Content-Type: text/plain` 和正文 `success`。

回调状态不能建模为永远不可逆：

- `SUCCESS` 可能变成 `REVERSED`；
- `FAILED` 可能后来变成 `SUCCESS`；
- `REFUND` 和已验签的未知状态应保存并隔离账务影响，然后查询 TDayPay。

## 12. 响应与重试原则

- HTTP 200 只代表 HTTP 请求成功；
- `resultCode=000000` 只代表 API 接受请求；
- 最终交易结果应以回调和主动查询得到的订单状态为准；
- 网络超时、`999998` 或其他不明确结果必须先查询；
- `400000` 表示重复提交，不能盲目生成新订单；
- 对 `errorCode` 和 `errorMsg` 保留诊断价值，但输出时必须脱敏。

## 13. 国家规则示例

### 13.1 哥伦比亚 COP

- 代收和出款金额不支持小数；
- 文档范围为 5,000–3,000,000 COP，但公开示例存在冲突；
- `PSE` 只作为代收侧别名规范化为 `NET_BANKING`，不能用于出款别名；
- COP 代收使用公共字段 `firstname`、`lastname`，不要创建额外的 `firstName`、`lastName`；
- `NET_BANKING` 代收需要文档码表中的数字 `bankCode`；
- `TRANSFIYA` 出款使用 10 位本地手机号作为账户；
- Bre-B 出款使用已注册的 key，不能根据值的外观猜测 key 类型。

### 13.2 墨西哥 MXN

- SPEI 代收要求 `dynamic=4`；
- SPEI 代收订单号不能包含 `_`；
- SPEI 出款使用 18 位 CLABE，并验证 3/7/1 校验位；
- CLABE 格式正确不代表账户存在或属于目标收款人；
- 公开金额示例与文字范围存在冲突时，生产前需要合同确认。

## 14. 验证 Skill 和集成辅助工具

```bash
python3 scripts/country_rules.py audit --max-source-age-days 365
python3 scripts/country_rules.py selftest
python3 scripts/tdaypay_callback.py selftest
python3 scripts/integration_selftest.py
```

预期结果：

- 规则目录结构和来源有效；
- 国家规则代表性正反用例通过；
- 回调签名和字段验证用例通过；
- 项目检查、规则注释、请求准备等集成自检通过。

这些测试验证的是确定性规则，不代表某个商户已经开通渠道，也不代表生产交易一定成功。

## 15. 常见问题

### 为什么已经返回 `orderId`，订单还不是成功？

`orderId` 和 `resultCode=000000` 只证明创建请求被接受。最终结果仍需要回调或订单查询确认。

### 为什么签名验证失败？

优先检查：

- 签名和发送是否使用同一份 JSON 字节；
- JSON 是否在签名后被重新格式化；
- `timestamp` 是否为秒；
- `method` 是否与操作匹配；
- 商户 ID、密钥和网关是否属于同一环境；
- 回调是否错误地使用了出站请求签名公式。

### 请求超时后可以直接重试吗？

不可以。创建请求的结果可能不明确，应先使用平台 `orderId` 或已保存的订单关联查询状态，避免重复出款或重复收款订单。

### 为什么格式校验通过仍不能生产发送？

`valid: true` 只表示本地能够执行的确定性规则通过。渠道开通、账户归属、钱包激活、银行限额和商户合同无法仅通过请求 JSON 证明。

### 出款是否必须增加人工审核？

不是。默认沿用项目现有的授权流程，并在确定性校验后直通执行。只有业务本来就有审核流程，或用户明确要求新增时，才增加人工审核。

### 代码中的 `TDAYPAY-RULE` 注释可以删除吗？

不建议。它们记录了强制校验的规则编号、行为、来源和核验日期。规则目录变化时，应重新生成注释计划并检查代码覆盖，而不是手工保留过期注释。

## 16. 更新规则时的要求

更新 `references/rules.json` 时，应同时完成：

1. 使用当前 TDayPay 官方文档或商户书面合同；
2. 记录来源、核验日期、适用动作和冲突；
3. 不从其他国家推断缺失字段；
4. 区分 TDayPay API 规则和国家支付网络事实；
5. 增加或修改对应正反测试；
6. 重新运行规则审计、自检和 Skill 结构验证；
7. 重新生成受影响渠道的 `TDAYPAY-RULE` 注释。

## 17. 参考资料

- `SKILL.md`：完整工作流和生产边界。
- `references/api-contract.md`：网关、请求头、签名、响应和状态。
- `references/fields.md`：公共请求字段。
- `references/country-catalog.md`：国家和渠道规则。
- `references/callback-validation.md`：回调实现要求。
- `references/integration-guidance.md`：项目适配与模块设计建议。
- [TDayPay 官方 Postman 文档](https://documenter.getpostman.com/view/10814992/2s93XyTNoA)。

---

README 生成日期：2026-09-17  
Skill 规则快照核验日期：2026-09-10
