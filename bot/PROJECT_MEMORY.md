# edgeX Agent Bot — 项目记忆文档

> **一句话定位：** 告诉它你怎么想，它帮你交易。
>
> 一个 Telegram 机器人，将自然语言的市场观点转化为 edgeX 永续合约交易所的实盘交易。
> 用户说"BTC看起来要涨，帮我做多" → AI 生成交易计划 → 用户确认 → 在 edgeX 上下单执行。

---

## 目录

1. [产品愿景](#1-产品愿景)
2. [用户体验流程](#2-用户体验流程)
3. [Bot 命令一览](#3-bot-命令一览)
4. [技术架构与文件](#4-技术架构与文件)
5. [AI 系统设计](#5-ai-系统设计)
6. [edgex-cli 集成](#6-edgex-cli-集成)
7. [数据库设计](#7-数据库设计)
8. [部署与运维](#8-部署与运维)
9. [测试体系](#9-测试体系)
10. [已知问题与待办](#10-已知问题与待办)
11. [关键决策与踩坑经验](#11-关键决策与踩坑经验)

---

## 1. 产品愿景

**目标用户：** 想在 edgeX 上交易但觉得交易所界面太复杂的加密/股票交易者。他们有市场观点，但不想手动设置入场价、止盈止损、杠杆、仓位大小。

**核心价值：**
- 自然语言输入（中/英文）→ 精准的交易计划输出
- AI 负责数学计算（入场价、TP/SL、仓位大小、杠杆），基于用户的观点
- 用户只需确认或取消——一键交易
- 在 Telegram 里运行，7x24小时，无需下载任何 App

**商业模式：**
- 免费层：每日 1000 次 AI 调用（由 Factory Droid / DeepSeek 驱动）
- 用户可配置自己的 API Key（OpenAI、Anthropic、Gemini、DeepSeek）实现无限调用
- 未来：edgeX 积分 / 订阅制

**edgeX 简介：**
- edgeX 是一个去中心化永续合约交易所（类似 dYdX/Hyperliquid）
- 290+ 合约：加密货币（BTC、ETH、SOL...）+ 美股（TSLA、AAPL、NVDA...）
- 全仓保证金，USDT 作为抵押品，每 1-4 小时结算资金费率
- 基于 StarkEx L2，需要 stark_private_key 签名交易

---

## 2. 用户体验流程

### 新用户首次使用
```
用户打开 @edgeXAgentBot → /start
  → "欢迎！连接你的 edgeX 账户"
  → [⚡ 使用 edgeX 登录] (OAuth — 规划中)
  → [🔑 使用 API Key 连接] (当前方式)
    → 输入 Account ID → 输入 L2 privateKey → 验证 → 连接成功！
```

### 老用户
```
用户打开 bot → /start → 仪表盘（账户信息、快捷操作）
用户输入："ETH看起来要跌了 帮我做空"
  → [持续打字指示器 20-30秒，AI 处理中]
  → AI 交易计划：
      📊 ETH 交易计划
      方向：SELL（做空）
      入场：$3,450 | TP：$3,200 | SL：$3,550
      仓位：0.03 ETH（~$103.50）| 杠杆：3x
      信心度：HIGH
      [✅ 确认执行] [❌ 取消]
  → 用户点击确认 → 在 edgeX 下单 → 确认消息
```

### 价格查询（不交易）
```
用户："BTC现在多少钱"
  → "BTC 目前价格约 $95,432，24小时涨幅 +2.3%，成交量 $1.2B"
  （没有确认/取消按钮——纯信息展示）
```

### 策略咨询
```
用户："crcl涨了很多，有什么操作机会吗"
  → AI 给出真实的市场分析：当前价格、涨幅、资金费率、建议的 2-3 种策略、风险提示
  （对话式回复，不是模板化的固定消息）
```

---

## 3. Bot 命令一览

| 命令 | 功能 | 处理函数 |
|------|------|----------|
| `/start` | 仪表盘（已登录）或引导登录流程 | `cmd_start`（ConversationHandler）|
| `/status` | 账户余额 + 持仓 | `cmd_status` |
| `/pnl` | 盈亏报告 | `cmd_pnl` |
| `/history` | 最近交易记录 | `cmd_history` |
| `/close` | 关闭某个持仓 | `cmd_close`（显示持仓选择器）|
| `/help` | 列出所有命令 | `cmd_help` |
| `/setai` | 配置 AI 提供商（OpenAI/Anthropic/Gemini/DeepSeek）| `cmd_setai` |
| `/cancel` | 取消当前设置流程 | `cancel_setup` |

**任何自由文本消息** 都会交给 AI 引擎处理（`handle_message`）。

---

## 4. 技术架构与文件

### 服务器
- **主机：** Oracle Cloud 实例 `147.224.247.125`
- **用户：** `ubuntu`
- **路径：** `/home/ubuntu/edgex-agent-bot/`
- **Python：** 3.10 + venv 虚拟环境
- **服务：** systemd `edgex-agent`
- **Bot 用户名：** `@edgeXAgentBot`

### 文件结构

```
edgex-agent-bot/
├── main.py              (1250 行) — Telegram 消息处理、会话流程、交易执行
├── ai_trader.py         (730 行)  — AI 引擎、系统提示词、edgex-cli、所有 LLM 供应商
├── edgex_client.py      (196 行)  — edgeX Python SDK 封装（余额、下单、持仓）
├── config.py            (41 行)   — 环境变量、安全限制、合约ID映射
├── db.py                (135 行)  — SQLite 存储（用户、交易、AI用量）
├── test_bot.py          (187 行)  — 单元测试（43 个测试）
├── tg_regression.py     (198 行)  — 基于 Telethon 的自动化回归测试（22 个测试）
├── requirements.txt                — Python 依赖
├── .env                            — 密钥（BOT_TOKEN、DEEPSEEK_API_KEY 等）
├── edgex_agent.db                  — SQLite 数据库
├── tg_test_session.session         — Telethon 会话文件（自动测试用）
└── venv/                           — Python 虚拟环境
```

### main.py — 核心模块

| 模块 | 功能 |
|------|------|
| `cmd_start` + ConversationHandler | 登录流程：OAuth 规范 → API Key → 验证 → 存入 DB |
| `handle_message` | AI 核心循环：打字指示器 → AI 调用 → 解析响应 → CHAT 回复或 TRADE 确认 |
| `_keep_typing()` | 每 4 秒发送 typing 动作，AI 处理期间保持（防止界面"死掉"）|
| `confirm_trade_callback` | 通过 edgeX SDK 执行确认的交易 |
| `cmd_status` | 从 edgeX SDK 获取账户余额 + 持仓 |
| `cmd_pnl` | 计算盈亏（持仓 + 交易历史）|
| `cmd_history` | 显示最近的成交记录 |
| `cmd_close` | 关闭指定持仓 |
| `cmd_setai` | AI 提供商配置（内联键盘选择 OpenAI/Anthropic/Gemini）|
| 快捷操作回调 | `quick_status`、`quick_pnl`、`quick_history`（/start 仪表盘按钮触发）|

### ai_trader.py — AI 引擎

| 模块 | 功能 |
|------|------|
| `SYSTEM_PROMPT_TEMPLATE` | 2000+ token 系统提示词（edgex-cli 命令、交易规则、响应格式、示例）|
| `get_live_contracts()` | 通过 edgex-cli 并发获取 30 个热门合约，缓存 1 小时 |
| `get_market_context()` | 获取提及资产的实时行情数据（注入到提示词中）|
| `run_edgex_cli()` | edgex-cli 子进程的异步封装 |
| `generate_trade_plan()` | 调度器：构建提示词 → 调用 AI → 解析响应 |
| `_parse_content()` | 从 AI 响应中提取 JSON（处理 markdown 栅栏、嵌套 JSON、回退机制）|
| `_normalize()` | 验证交易计划：缺少 side/size → 转为 CHAT，**保留 AI 原始内容** |
| `validate_plan()` | 安全检查：最大仓位、最大杠杆、有效方向。无效 → 转为 CHAT |
| `call_factory_api()` | 免费层：调用 Factory Droid exec，剥离 `\x07` BEL 字符，解析 wrapper |
| `call_openai_api()` | OpenAI 兼容接口（DeepSeek、Groq 等）|
| `call_anthropic_api()` | Anthropic Claude 接口 |
| `call_gemini_api()` | Google Gemini 接口 |

### edgex_client.py — edgeX SDK 封装

轻量异步封装 `edgex-python-sdk`：
- `create_client(account_id, stark_private_key)` — 创建 SDK 客户端
- `get_account_summary(client)` — 余额 + 持仓
- `get_price(client, contract_id)` — 24 小时行情
- `place_order(client, contract_id, side, size, price)` — 限价单
- `cancel_order(client, account_id, order_id)` — 撤单
- `close_position(client, contract_id, position)` — 通过反向订单平仓
- `validate_credentials(account_id, stark_private_key)` — 验证登录

---

## 5. AI 系统设计

### 响应类型

AI 必须返回 **纯 JSON**（无 markdown）。两种类型：

```json
// CHAT — 价格查询、分析、策略讨论、任何非交易操作
{"action": "CHAT", "reply": "BTC 目前约 $95,000，24h +2.3%"}

// TRADE — 仅当用户明确要求买/卖/做多/做空时
{"action": "TRADE", "asset": "BTC", "side": "BUY", "size": "0.001",
 "leverage": "3", "entry_price": "95000.0", "take_profit": "98000.0",
 "stop_loss": "93000.0", "confidence": "HIGH",
 "reasoning": "用户看多BTC，建议小仓位做多...", "position_value_usd": "95.0"}
```

### AI Agent 理念（关键！）

AI 不是模板机器。它是真正的对话式交易助手：
- 价格查询 → 给出具体数字 + 市场分析
- 策略咨询（"crcl涨了有什么操作"）→ 分析市场、建议 2-3 种策略、提示风险
- 只有明确的交易指令才走 TRADE 确认流程
- AI 可以自由分析、发表观点、建议策略——**永远不要用硬编码的模板消息替换 AI 的回复**

### AI 供应商路由

1. **免费层（默认）：** Factory Droid exec → 底层是 DeepSeek。每日 1000 次限制。
2. **用户自己的 Key：** `/setai` → 选择供应商 → 输入 API Key → 存入 DB。
   - OpenAI 兼容（DeepSeek、Groq、OpenRouter 等）
   - Anthropic（Claude）
   - Google Gemini

### 关键解析逻辑（`_parse_content` + `_normalize`）

AI 有时返回格式不正确的 JSON。解析链：
1. 剥离 `droid exec` 输出的 BEL 字符 (`\x07`)
2. 去除 markdown 代码栅栏 (```json ... ```)
3. 尝试 `json.loads(content)` 直接解析
4. 文本中查找 JSON：`{...}` 提取
5. 正则：查找 `{"action":...}` 或 `{"asset":...}` 模式
6. 回退：将整个文本作为 CHAT 回复

`_normalize()` 处理残缺的交易计划：
- 有 `asset` + 有效 `side` + `size` → 保持 TRADE
- 有 `asset` 但 side/size 无效/缺失 → 转为 CHAT，**保留 AI 的 reply/reasoning**

`validate_plan()` 是最后一道安全网：
- 无效 side → 转为 CHAT，使用 AI 原始内容
- 仓位价值 > $500 → 报错
- 杠杆 > 5x → 报错

### 打字指示器

`_keep_typing()` 在后台每 4 秒发送 Telegram "typing" 动作，直到 AI 响应完成。这避免了 20-30 秒 AI 处理期间界面看起来"卡死"的问题。

---

## 6. edgex-cli 集成

**是什么：** npm 包 `@realnaka/edgex-cli` (v0.1.0) — edgeX 交易所的命令行工具。
**源码：** https://github.com/realnaka/edgex-cli
**路径：** `/home/ubuntu/.npm-global/bin/edgex`

### 使用方式

1. **动态合约列表：** `get_live_contracts()` 并发调用 `edgex --json market ticker <symbol>` 获取 30 个热门合约，缓存 1 小时。注入到 AI 系统提示词中，让 AI 知道当前价格。

2. **实时行情上下文：** `get_market_context()` 获取用户消息中提及的资产的行情数据（例如"BTC"或"crcl"）。注入到提示词中。

3. **代币解析：** edgex-cli 支持 290+ 合约。接受代币名（BTC）、合约名（BTCUSD）或合约 ID（10000001）。

### 为什么用 edgex-cli 而不是纯 SDK

Python SDK（`edgex-python-sdk`）大多数调用需要鉴权。edgex-cli 无需鉴权即可获取公开市场数据，支持 `--json` 输出，命令更丰富（K线、资金费率、深度、多空比等）。

---

## 7. 数据库设计

SQLite，文件位置 `edgex_agent.db`：

```sql
-- 用户凭证
users (
  tg_user_id INTEGER PRIMARY KEY,   -- Telegram 用户 ID
  account_id TEXT,                    -- edgeX 账户 ID（如 "713029548781863066"）
  stark_private_key TEXT,             -- L2 签名密钥（hex，敏感数据！）
  ai_api_key TEXT,                    -- 用户自己的 AI API Key（可选）
  ai_base_url TEXT,                   -- AI 供应商地址（可选）
  ai_model TEXT,                      -- AI 模型名（可选）
  created_at REAL                     -- Unix 时间戳
)

-- 交易记录
trades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_user_id INTEGER,
  order_id TEXT,
  contract_id TEXT,
  side TEXT,          -- BUY 或 SELL
  size TEXT,
  price TEXT,
  status TEXT,        -- OPEN, FILLED, CANCELLED
  pnl TEXT DEFAULT '0',
  thesis TEXT,        -- 用户原始消息 / AI 推理
  created_at REAL,
  updated_at REAL
)

-- AI 用量追踪（限流）
ai_usage (
  tg_user_id INTEGER,
  date TEXT,           -- YYYY-MM-DD
  count INTEGER DEFAULT 0,
  PRIMARY KEY (tg_user_id, date)
)
```

---

## 8. 部署与运维

### 服务器访问

```bash
ssh -i ~/Downloads/ssh-key-2026-02-20.key ubuntu@147.224.247.125
```

### systemd 服务

```bash
# 服务文件：/etc/systemd/system/edgex-agent.service
# ExecStart: /home/ubuntu/edgex-agent-bot/venv/bin/python3 -u main.py
# WorkingDirectory: /home/ubuntu/edgex-agent-bot

sudo systemctl restart edgex-agent       # 重启
sudo systemctl status edgex-agent        # 查看状态
sudo journalctl -u edgex-agent -f        # 实时日志
sudo journalctl -u edgex-agent --since "10 min ago"  # 最近日志
```

### 部署流程

```bash
# 1. 本地编辑文件：~/Desktop/aaron/edgeXAgent/bot/
# 2. 上传到服务器：
scp -i ~/Downloads/ssh-key-2026-02-20.key \
  ai_trader.py main.py config.py \
  ubuntu@147.224.247.125:~/edgex-agent-bot/

# 3. 重启：
ssh -i ~/Downloads/ssh-key-2026-02-20.key ubuntu@147.224.247.125 \
  'sudo systemctl restart edgex-agent'

# 4. 运行回归测试：
ssh -i ~/Downloads/ssh-key-2026-02-20.key ubuntu@147.224.247.125 \
  'cd ~/edgex-agent-bot && source venv/bin/activate && python3 tg_regression.py'
```

### 环境变量（.env）

```
TELEGRAM_BOT_TOKEN=<从 @BotFather 获取的 bot token>
DEEPSEEK_API_KEY=<Factory Droid exec key — 免费层使用>
DEEPSEEK_BASE_URL=https://api.deepseek.com
EDGEX_BASE_URL=https://pro.edgex.exchange
EDGEX_WS_URL=wss://quote.edgex.exchange
```

### 依赖

```
python-telegram-bot[ext]>=21.0,<22.6
edgex-python-sdk>=0.3.0
python-dotenv>=1.0.0
aiohttp>=3.9.0
httpx>=0.25.0
# 测试：telethon（安装在 venv 中）
# CLI：@realnaka/edgex-cli（npm 全局安装）
```

---

## 9. 测试体系

### 单元测试（test_bot.py）

```bash
cd ~/edgex-agent-bot && source venv/bin/activate
python3 -m pytest test_bot.py -v
# 43 个测试：DB 操作、配置、edgeX 客户端、AI 引擎、edgex-cli 集成
```

### 回归测试（tg_regression.py）

通过 Telethon MTProto API 进行端到端自动化测试。以真实 Telegram 用户身份登录并向 bot 发消息。

```bash
python3 tg_regression.py
# 22 个测试，9 个场景：
#   1. /start（已登录用户的仪表盘）
#   2. /status（余额信息）
#   3. /help（命令列表）
#   4. /pnl（盈亏报告）
#   5. /history（交易历史）
#   6. AI — BTC 价格查询（自然语言，提及 BTC/$）
#   7. AI — CRCL 识别（不与 CRV 混淆）
#   8. AI — 策略咨询（真实分析，非模板回复）
#   9. AI — 交易确认流程（BUY BTC 计划）
```

**Telethon 会话：** `tg_test_session.session`（已用 +85365712199 认证）
**Telegram API：** api_id=<configured via env>

### 手动测试要点

打开 Telegram → @edgeXAgentBot → 发消息。关键测试用例：
- "BTC现在多少钱" → 应返回价格（CHAT，无确认按钮）
- "crcl现在什么价格" → 应提及 CRCL（不是 CRV）
- "帮我做多BTC 小仓位" → 应显示交易计划 + 确认/取消按钮
- "ETH looks bearish" → 应给出分析（CHAT）
- "crcl涨了有什么操作" → 应给出市场分析和策略建议（CHAT）
- "short ETH 100u" → 应显示交易计划（TRADE）

---

## 10. 已知问题与待办

### 已完成
- [x] 修复原始 JSON 输出泄露（`{"type":"result",...}` wrapper 直接发给用户）
- [x] 修复 CRCL ≠ CRV 代币混淆
- [x] 打字指示器（每 4 秒持续发送）
- [x] 确认流程（AI 必须展示计划，用户必须确认）
- [x] 修复价格查询显示确认按钮
- [x] 移除 `get_prices_for_all()` 瓶颈（每条消息 48 次 SDK 请求）
- [x] 修复 BEL 字符 (`\x07`) 导致 `droid exec` JSON 解析失败
- [x] AI 从模板机器改造为真正的对话式 Agent
- [x] `_normalize` 和 `validate_plan` 不再覆盖 AI 原始回复
- [x] 自动化回归测试（22/22 通过）

### 待办
- [ ] **OAuth 登录：** 规范已写好（在 /start → "使用 edgeX 登录"），等待 edgeX 团队实现
- [ ] **Token 轮换：** Bot token 在早期开发中被暴露过——需要轮换
- [ ] **监控告警：** 目前没有 bot 宕机告警（只有 systemd 自动重启）
- [ ] **edgex-cli 限流：** CLI 调用被限流时没有重试/退避逻辑
- [ ] **WebSocket 推送：** 目前通过 CLI 轮询。实时价格提醒需要 WS
- [ ] **交易执行：** 目前只支持限价单（SDK）。市价单需要 edgex-cli
- [ ] **持仓同步：** `trades` 表未与交易所状态完全同步

### 未来功能
- 实时价格提醒（"BTC到10万美元时通知我"）
- 投资组合分析（"我的持仓怎么样"）
- 跟单交易（"跟着这个大户操作"）
- 多步 AI 工作流（分析 → 决策 → 执行 → 监控）
- Telegram Mini App（更丰富的 UI 体验）

---

## 11. 关键决策与踩坑经验

### 为什么选 Telegram Bot（而不是 Web App）？
- 零摩擦：用户已经有 Telegram
- 自然语言 UX 天然适合聊天界面
- 通知功能内建（价格提醒、订单成交）
- edgeX 用户群在 Telegram 上很活跃

### 为什么用 Factory Droid 做免费层？
- 免费 AI 调用，用户无需自己的 API Key
- 底层模型选择透明——Factory 路由到最优模型
- 每日 1000 次限制，防止滥用的同时保持可用性

### 为什么用 edgex-cli 而不是纯 SDK？
- SDK 大多数调用需要鉴权；CLI 无需鉴权获取公开数据
- CLI 支持 `--json` 输出，解析方便
- CLI 动态解析 290+ 代币（SDK 只有静态合约 ID）
- 数据更丰富：K线、资金费率历史、多空比

### AI 响应解析很难
AI（尤其是小模型）经常返回格式不正确的 JSON，或者对非交易查询返回交易 JSON。防御链：
1. 剥离 `droid exec` 输出的 BEL 字符 (`\x07`)
2. 去除 markdown 代码栅栏
3. 多重 JSON 提取尝试（直接解析、子串、正则）
4. `_normalize()` 捕获不完整的交易计划 → 转为 CHAT，**保留 AI 原始内容**
5. `validate_plan()` 最后安全网——无效交易转为 CHAT
6. `handle_message` 在验证后重新检查 action（关键！）

### AI 必须是 Agent，不是模板机器
早期版本对任何非交易请求都返回硬编码消息（"I need a clearer direction. Try: 'long BTC' or 'short ETH'"）。这严重伤害了用户体验——询问策略、市场分析甚至价格的用户都得到了机器人般的回复。修复：重写系统提示词，让 AI 成为真正的对话式 Agent。它可以自由分析、讨论、建议——只有实际交易执行才需要用户确认。**永远不要用硬编码消息替换 AI 的回复。**

### 打字指示器很重要
如果没有持续的 typing 动作（每 4 秒），用户会在 20-30 秒 AI 处理期间看到一个"死掉"的聊天界面。这让 bot 看起来像是坏了。`_keep_typing()` 后台任务对 UX 至关重要。

---

### BWEnews Telethon 会话管理（重要！）
- `bwenews_mcp.py` 使用 Telethon 连接 @BWEnews 频道获取新闻
- 会话文件 `bwenews_session.session` 是排他的 — **绝不能同时从两个进程访问**
- 如果另一个脚本/测试尝试使用同一个会话文件，会触发 `AuthKeyDuplicatedError`，导致会话永久失效
- 修复方法：删除 `.session` 文件，用 `auth_bwenews.py` 重新认证（需要手机验证码）
- TG API 凭证：`TG_API_ID`=32692718，关联手机 +85365712199
- 架构改为轮询模式（`get_messages` 每30秒拉取），比事件监听更可靠

### AI 系统 CRITICAL RULES（绝不能违反）
- **绝不能更改用户请求的资产** — 用户说"做多BTC"，AI 必须用 BTC。余额不足时回复 CHAT 解释，不能偷偷换成别的币
- **TRADE 响应必须所有字段都填满** — asset, side, size, leverage, entry_price, take_profit, stop_loss, confidence, reasoning, position_value_usd
- **TP/SL 是强制的** — 根据市场波动率计算合理的 TP/SL。典型范围：TP +5-15%，SL -3-8%

### 订单显示规范
- edgeX API 返回 BUY/SELL，但 UI 必须显示 LONG/SHORT（永续合约标准）
- 使用 `_side_label()` 辅助函数转换，应用于所有 7 个订单显示位置

*最后更新：2026-03-05*
*Bot：Telegram @edgeXAgentBot*
*服务器：ubuntu@147.224.247.125:/home/ubuntu/edgex-agent-bot/*
