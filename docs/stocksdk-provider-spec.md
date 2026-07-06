# stock-sdk 数据源接入 SPEC

> 目标：新增一个内置数据源 `stocksdk`，作为付费依赖 **tickflow** 的免费平替，覆盖日K、除权因子、分钟K、实时行情、标的列表五类核心行情数据。用户可在「设置 → 数据源」里一键切换。

## 1. 背景与约束

- **tickflow 是付费项目**：日K免费，除权因子/分钟K/财务等需 Starter+ 档位付费 key。
- **stock-sdk 是零依赖的 Node/JS SDK**（npm 包 `stock-sdk`），封装腾讯/东财等公开行情接口，提供 A股/港股/美股/基金的行情、K线、指标、资金流、龙虎榜等数据，并自带 CLI 与 MCP server。数据免费、无需 key。
- **后端是 Python**（FastAPI + Polars + DuckDB），Docker 运行时为 `python:3.11-slim`，**默认无 Node**。
- **stock-sdk 不提供财务报表**（income/balance_sheet/cash_flow）→ 财务数据集不在本次范围，`financial` provider 保持回退 tickflow。

### 桥接决策（已确认）
Python 后端通过 **subprocess 调用打包的 Node 桥接脚本 `bridge.mjs`**，脚本 `import` 真实 stock-sdk，按批并发抓取后以 JSON 输出到 stdout。用真实 SDK → 符号解析/复权逻辑全对、维护成本低。代价：运行镜像需装 Node + stock-sdk（Dockerfile 增改），每批一次进程启动开销（可接受，批内并发摊薄）。

## 2. 现有 Provider 架构（复用点）

- **Provider 契约**：`app/data_providers/base.py` 的 `MarketDataProvider`（Protocol）。归一化 schema 在 `normalizer.py`：
  - `DAILY_COLS = symbol,date,open,high,low,close,volume,amount`
  - `ADJ_FACTOR_COLS = symbol,trade_date,ex_factor`
  - `INSTRUMENT_COLS = symbol,name,code,exchange,asset_type,source`
- **运行时分流**（关键）：各 service（`kline_sync`/`quote_service`/`financial_sync`）按数据集独立选源：
  ```python
  provider_name = preferences.get_daily_data_provider()      # 默认 "tickflow"
  if provider_name != "tickflow":
      from app.data_providers import custom as custom_sources
      if custom_sources.provider_has_dataset(provider_name, "daily"):
          provider = custom_sources.get_provider(provider_name)
          df = provider.get_daily(symbols, start_time=..., end_time=..., on_chunk_done=...)
      # 未配置该数据集 → 回退 tickflow
  ```
  即：**任何非 `tickflow` 的源都从 `custom_sources` 注册表按名字取**。`preferences._allowed_data_providers() = {"tickflow"} | custom_sources.names()`。
- **Provider 方法签名**（service 实际调用的是 `GenericHTTPProvider` 那套，非 Protocol）：
  - `get_daily(symbols, start_time, end_time, asset_type="stock", on_chunk_done=None) -> pl.DataFrame`
  - `get_adj_factors(symbols, start_time, end_time, asset_type="stock", on_chunk_done=None) -> pl.DataFrame`
  - `get_minute(symbols, start_time, end_time, asset_type="stock", on_chunk_done=None) -> pl.DataFrame`
  - `get_realtime() -> list[dict]`（无参，拉全市场；字段需含 `symbol,last_price,prev_close,open,high,low,volume`）
  - `test_dataset(dataset, symbols) -> dict`、`close()`、`.name`、`.config.datasets/.display_name/.path`

### 核心接入策略：零 service 改动
把 `stocksdk` 作为**内置 provider 注入 `custom.loader._PROVIDERS`**（但标记为 builtin，不出现在「自定义源」列表、不可编辑/删除）。这样 `names()/get_provider()/provider_has_dataset()` 自动包含它，**所有 service 分流点无需改动**。仅标的同步（`instrument_sync`）走 tickflow 直连、无分流，需单独加一个 stocksdk 分支。

## 3. stock-sdk 能力核对（实测）

| 需求 | stock-sdk 用法 | 输出要点 |
|---|---|---|
| 日K | `sdk.kline.cn(sym,{period,adjust:'none',start,end})` | `date(YYYY-MM-DD),open,high,low,close,volume,amount,...,code` |
| 除权因子 | 同上取 `adjust:'hfq'` 与 `'none'`，`ex_factor = close_hfq/close_none` 按日合成 | 首日因子=1，后续放大 |
| 分钟K | `sdk.kline.minute(sym,{period:5})` | `date('YYYY-MM-DD HH:mm'),open,high,low,close,volume,amount` |
| 实时全市场 | `sdk.batch.cn({concurrency})` | 5500+ 只，含 `code,name,marketId,price,prevClose,open,high,low,volume,amount,...` |
| 标的列表 | `sdk.batch.cn()`（股票）| `code,name,marketId`（1=SH,51=SZ,62=BJ）、`totalShares,circulatingShares,limitUp,limitDown` |

- **符号容错**：stock-sdk 直接接受 `600519.SH`/`000001.SZ` 写法，日K返回 `code`（无后缀）。→ 桥接对 daily/minute/adj **回显调用方传入的 app 符号**，避免映射歧义；对 realtime/instruments 由 `code+marketId` 反推后缀（1→.SH, 51→.SZ, 62→.BJ）。
- **market 覆盖**：index（`000001.SH` 上证）、etf（`510300`）日K同接口可取。realtime `batch.cn` 仅股票，指数/ETF 实时仍走 tickflow 各自路径（本期不改）。

## 4. 交付物（文件清单）

### 4.1 新增 — 后端 stocksdk provider 包
```
backend/app/data_providers/stocksdk/
  __init__.py        # 导出 StockSDKProvider / build_provider / availability
  bridge.mjs         # Node 桥接脚本：stdin JSON job → stdout JSON
  bridge.py          # subprocess 封装：解析 node / 定位 stock-sdk / 跑 job / 解析结果
  provider.py        # StockSDKProvider：调 bridge + 归一化到内部 schema
  package.json       # 声明 stock-sdk 依赖（供镜像内 npm i / 供 vendored node_modules）
```

**bridge.mjs 协议**：读 stdin 一行 JSON `{op, symbols?, adjust?, period?, start?, end?, concurrency?}`，`op ∈ {daily, adj, minute, realtime, instruments, ping}`；输出 `{ok:true, op, rows:{[appSymbol]: Row[]}}`（daily/adj/minute）/ `{ok:true, rows:Row[]}`（realtime/instruments）/ `{ok:false, error}`。内部用 `Promise` 并发池（`concurrency` 默认 6）逐符号抓取，异常降级为空数组不整体失败。

**bridge.py**：
- 定位 `node`（`STOCK_SDK_NODE` env > `shutil.which("node")`）。
- 定位 stock-sdk：脚本同目录 `node_modules/stock-sdk`（vendored）> 全局。桥接以脚本目录为 CWD，保证 `import 'stock-sdk'` 可解析。
- `run_job(job: dict, timeout=...) -> dict`：`subprocess.run([node, bridge.mjs], input=json, capture, timeout)`；非零退出/超时/解析失败 → 抛 `StockSDKBridgeError`。
- `availability() -> (bool, reason)`：跑 `{op:'ping'}` 探活，供 UI/日志用。

**provider.py `StockSDKProvider`**：
- `name="stocksdk"`；`.config`=轻量 shim（`display_name="stock-sdk（免费行情）"`, `datasets={daily,adj_factor,minute,realtime}`, `path=None`, `builtin=True`）。
- `get_daily/get_minute`：桥接 `daily/minute` → 每 symbol rows 打上 `symbol` → `normalize_daily`/minute 归一化 → concat。分批 + `on_chunk_done` 回调。
- `get_adj_factors`：桥接 `adj`（内部取 hfq/none 合成 `ex_factor`）→ `normalize_adj_factors`。
- `get_realtime()`：桥接 `instruments`→不，`realtime`（`batch.cn`）→ map 到 `symbol,last_price,prev_close,open,high,low,volume,name,amount,...` 的 dict 列表。
- `get_instruments(asset_type="stock") -> list[dict]`：桥接 `instruments` → `symbol,name,code,exchange,region,type,...` 兼容 `instrument_sync` 的 flatten 行。
- `test_dataset(dataset, symbols)`：跑对应 op，返回 `{provider,dataset,rows,columns,preview}`。
- `close()`：no-op。

### 4.2 改动 — 注册与分流
- `custom/loader.py`：`load_all()` 末尾 `_register_builtins()` 注入 stocksdk；`list_sources()` 过滤 builtin；`save_config/delete_config/get_config_dict` 对 builtin 名字报错/返回 None。`_BUILTIN` 集合。
- `services/instrument_sync.py`：`sync_instruments()` 开头按 `get_daily_data_provider()` 分流：非 tickflow 且 provider 有 `get_instruments` → 用之，否则 tickflow 直连。
- `services/preferences.py`：无需改（`names()` 已含 stocksdk）。

### 4.3 改动 — API
- `api/settings.py` `list_data_sources()`：`builtin` 数组加入 stocksdk（含 `datasets` + `available` 状态）。`get/save/delete/test` 对 builtin 名字做保护（test 允许，走 provider.test_dataset）。

### 4.4 改动 — 前端
- `pages/settings/DataSources.tsx`：把「是否内置」判断从硬编码 `name==='tickflow'` 改为 `builtinNames.has(name)`；builtin 卡片不可编辑（点击不 `editExisting`）、显示「内置」徽标与数据集；`selected` 为 builtin 时渲染只读详情面板（tickflow 用原 `TickFlowDetail`，stocksdk 用新 `BuiltinDetail`/复用）。
- `lib/api.ts`：`DataSourceItem` 增补可选 `available?:boolean`、`description?:string`。

### 4.5 改动 — 部署 / 文档
- `Dockerfile` runtime 阶段：装 `nodejs`/`npm`，`npm i -g stock-sdk`（或在 provider 包内 `npm i` 生成 vendored node_modules 后 COPY）。设 `STOCK_SDK_NODE`（可选）。
- `docs/`：本 SPEC + 在 `docs/configuration.md`/`features.md` 补 stock-sdk 数据源说明；README 提一句。

### 4.6 测试
- `backend/tests/test_stocksdk_provider.py`：mock `bridge.run_job` 返回样例 → 验证 `get_daily/get_adj_factors/get_realtime/get_instruments` 归一化列与合成逻辑正确；`ex_factor=close_hfq/close_none`；符号回显；空结果处理。
- bridge.mjs 冒烟：`{op:'ping'}` 返回 ok（需 node，CI 可跳过）。

## 5. 数据流

```
用户在设置页点「使用 stock-sdk」
  → preferences.{daily,realtime,minute,adj}_data_provider = "stocksdk"
盘后 pipeline / 实时轮询 / 手动同步
  → service 分流命中 custom_sources.get_provider("stocksdk")
    → StockSDKProvider.get_xxx()
      → bridge.run_job() ──spawn──▶ node bridge.mjs ──import──▶ stock-sdk ──▶ 腾讯/东财
      ◀── JSON rows ──
    → normalize_* → pl.DataFrame（内部 schema）
  → 写 parquet / 更新缓存（与 tickflow 路径完全一致）
```

## 6. 边界与非目标
- 不改动 tickflow 逻辑；tickflow 仍为默认源。
- 财务/龙虎榜/资金流/涨停池等 stock-sdk 扩展数据本期不接（可后续扩 API 端点）。
- 指数/ETF 的**实时**仍走 tickflow；stocksdk 覆盖其**日K**（按符号）。
- Node/stock-sdk 缺失时：provider 注册仍在，UI 显示不可用，抓取时抛清晰错误并（在 service 层）回退 tickflow 行为不变。

## 7. 验收
1. 设置页出现「stock-sdk」内置卡片，可切换为当前源。
2. 切到 stocksdk 后：无 tickflow key 也能同步 A股日K、合成除权因子、拉分钟K、刷新实时全市场、同步标的列表。
3. 归一化后的 parquet 列与 tickflow 一致，下游指标/回测/看板正常。
4. Node 缺失时不 crash，日志与 UI 有明确提示。
5. 单测通过。
