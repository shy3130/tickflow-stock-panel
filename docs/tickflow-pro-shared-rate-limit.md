# TickFlow Pro 共享限频（Gold Shadow + A 股研究）

## 决策
- 同一 TickFlow API Key 的所有调用方必须共享进程级限频器：`backend/app/tickflow/rate_limits.py`。
- 项目安全预算 = 套餐额度 × **80%**（见 `tiers.yaml` 的 `pro` 段）。
- Gold Shadow Stage A 与 A 股同步/回测**不得**各建一套限频，避免叠加超限。

## 预算表示例（Pro）
| capability | 套餐 rpm | 80% 预算 |
|---|---:|---:|
| quote.batch | 120 | 96 |
| quote.pool | 60 | 48 |
| kline.daily.batch | 60 | 48 |
| kline.minute.batch | 30 | 24 |
| depth5.batch | 30 | 24 |
| adj_factor | 60 | 48 |

## 错峰
- 盘中（A 股交易时段）：优先保证 Gold Shadow 观察与 legacy 监控。
- 盘后：A 股日线/研究批量、分钟按需回填。
- 禁止全市场一年分钟一次性回填。

## 实现要点
- 调用方只传 `rpm`/`batch`，统一走 `sleep_between_batches` / `_reserve_slot`。
- 应用 80% 预算：在 resolve 后对 rpm 做 `floor(rpm * 0.8)`（后续 Phase 实现，Phase 0 仅冻结约定）。
- 任一 fallback / 429 必须写入 DatasetEvidence，禁止静默混源。
