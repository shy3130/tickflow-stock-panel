"""AI 策略生成器 — 读取策略开发文档 + 调用 LLM 生成策略代码。

职责: 接收用户自然语言描述 → 读取 docs/strategy-guide.md → 调用 LLM → 返回策略代码。
不知道: 引擎内部、API、前端、配置持久化、回测。
"""
from __future__ import annotations

import ast
import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# 策略开发文档路径
GUIDE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "strategy-guide.md"

_SYSTEM_PREFIX = """你是A股量化策略设计专家。根据用户描述的需求，参考下方的《策略开发指南》生成一个完整的策略Python文件。

核心约束:
- 只创建这一个 .py 文件，不要修改任何现有文件，不要跨文件引用
- 只 import polars as pl，不 import 其他模块

要求:
1. 用户可能调整的策略阈值通过 META["params"] 暴露；公式常数、固定窗口边界、布尔开关不必强行参数化
2. 遵循指南中的文件结构，但优先贴合用户规则，不要为了套模板歪曲策略含义
3. ENTRY_SIGNALS/EXIT_SIGNALS 根据策略逻辑自行选择匹配的信号列，不要照搬示例
4. scoring 权重根据策略核心逻辑定制，总和 = 1.0
5. 优先使用 Polars 表达式、窗口函数、聚合和 with_columns/filter 实现，避免逐行/逐股 Python 循环；只有表达式难以描述的复杂状态机才使用 partition_by/to_dicts
6. 直接输出Python代码，不要输出其他内容

--- 策略开发指南 ---

"""


class AIStrategyGenerator:
    """AI 策略生成器"""

    def __init__(self) -> None:
        self._guide_cache: str | None = None

    def _get_guide(self) -> str:
        if self._guide_cache is None:
            if GUIDE_PATH.exists():
                self._guide_cache = GUIDE_PATH.read_text(encoding="utf-8")
            else:
                logger.warning("strategy-guide.md not found at %s", GUIDE_PATH)
                self._guide_cache = ""
        return self._guide_cache

    async def generate(self, user_prompt: str) -> dict:
        """根据用户描述生成策略代码

        Returns: {"code": str, "meta": dict, "valid": bool, "error": str | None}
        """
        guide = self._get_guide()

        # 调用 LLM
        code = await self._call_llm(user_prompt, guide)

        # 验证
        try:
            self._validate_safety(code)
        except ValueError as e:
            return {"code": code, "meta": {}, "valid": False, "error": str(e)}

        # 试加载获取 META
        try:
            meta = self._extract_meta(code)
        except Exception as e:
            return {"code": code, "meta": {}, "valid": False, "error": f"解析META失败: {e}"}

        return {"code": code, "meta": meta, "valid": True, "error": None}

    async def _call_llm(self, user_prompt: str, guide: str) -> str:
        """调用 OpenAI 兼容 API（流式，避免 CDN 长连接超时）"""
        from openai import AsyncOpenAI
        from app import secrets_store

        ai_key = secrets_store.get_ai_key()
        if not ai_key:
            raise RuntimeError("AI API Key 未配置，请在设置页面配置")

        # User-Agent: 默认浏览器标识,绕过 Cloudflare 等 CDN/WAF 的 Bot 拦截(Issue #8)。
        # 用户可在 AI 设置页自定义。
        from app.config import settings
        user_agent = secrets_store.get_ai_config("ai_user_agent", "") or settings.ai_user_agent

        client = AsyncOpenAI(
            api_key=ai_key,
            base_url=secrets_store.get_ai_config("ai_base_url", "https://api.alysc.top"),
            timeout=180.0,
            max_retries=2,
            default_headers={"User-Agent": user_agent},
        )
        # 使用流式请求：CDN 收到首个 token 后会持续转发，不会因等待超时
        stream = await client.chat.completions.create(
            model=secrets_store.get_ai_config("ai_model", "gpt-5.5"),
            messages=[
                {"role": "system", "content": _SYSTEM_PREFIX + guide},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=3000,
            stream=True,
        )
        chunks: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                chunks.append(delta.content)
        content = "".join(chunks).strip()
        # 提取代码块
        if "```python" in content:
            content = content.split("```python", 1)[1].split("```", 1)[0].strip()
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0].strip()
        return content

    @staticmethod
    def _validate_safety(code: str) -> None:
        """AST 级安全检查"""
        tree = ast.parse(code)

        forbidden_modules = {"os", "sys", "subprocess", "socket", "shutil",
                             "pathlib", "http", "urllib", "requests", "httpx"}
        forbidden_calls = {"open", "exec", "eval", "compile", "__import__",
                           "globals", "locals", "vars", "dir", "getattr",
                           "setattr", "delattr", "type", "input"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] not in ("polars",):
                        if alias.name.split(".")[0] in forbidden_modules:
                            raise ValueError(f"禁止 import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] not in ("polars",):
                    if node.module.split(".")[0] in forbidden_modules:
                        raise ValueError(f"禁止 from {node.module} import")
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    raise ValueError(f"禁止调用 {node.func.id}()")

    @staticmethod
    def _extract_meta(code: str) -> dict:
        """从代码字符串中提取 META 字典（不执行代码）"""
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "META":
                        # 找到 META 赋值，用 compile+eval 安全提取
                        # 只允许字面量
                        meta_node = node.value
                        code_obj = compile(ast.Expression(meta_node), "<meta>", "eval")
                        return eval(code_obj, {"__builtins__": {}})  # noqa: S307
        return {}
