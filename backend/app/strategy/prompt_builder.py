"""策略提示词组装器 — 两步定制流程的提示词生成。

职责: 加载对应步骤的 Markdown 指南，拼接用户输入，组装 LLM 提示词。
不知道: LLM 调用、API、前端、引擎执行。
"""
from __future__ import annotations

from pathlib import Path

_DOCS_DIR = Path(__file__).resolve().parent / "prompts"
_cache: dict[str, str] = {}


def _load_doc(name: str) -> str:
    if name not in _cache:
        path = _DOCS_DIR / name
        _cache[name] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _cache[name]


DIRECTION_CN = {"long": "做多", "short": "做空", "monitor": "监控"}


def build_step1(name: str, description: str, direction: str, rules: str, strategy_id: str = "") -> str:
    """步骤1：规则 → 完整策略代码（参数 + 信号 + 评分 + 告警）

    注意: strategy-guide.md 已在 ai_generator.py 的 system prompt 中加载，
    此处不再重复加载以节省 token。
    """
    guide = _load_doc("strategy-builder-step1.md")

    id_line = f"\n策略ID（必须使用此ID）：{strategy_id}" if strategy_id else ""

    return f"""{guide}

---

请根据以下用户输入生成完整策略代码：

策略名称：{name}{id_line}
策略描述：{description}
选股方向：{DIRECTION_CN.get(direction, direction)}
策略规则：
{rules}

只输出 Python 代码。"""


def build_step2(current_code: str, instruction: str) -> str:
    """步骤2：修改策略任意部分"""
    guide = _load_doc("strategy-builder-step2.md")

    return f"""{guide}

---

当前策略代码：
```python
{current_code}
```

用户修改指令：
{instruction}

只输出修改后的完整 Python 代码。"""
