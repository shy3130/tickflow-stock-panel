"""Webhook 推送适配器 — 把告警事件推送到外部 IM / 量化软件。

职责: 把后端产生的告警事件, 通过用户配置的 Webhook 地址推送到外部。
     目前支持飞书群机器人; QMT / ptrade 等量化通道为待定。

飞书自定义机器人接入:
  1. 飞书群 → 群设置 → 群机器人 → 添加「自定义机器人」
  2. 复制生成的 Webhook 地址 (形如 https://open.feishu.cn/open-apis/bot/v2/hook/xxx)
  3. (可选) 安全设置 → 启用「签名校验」, 记录签名密钥(secret)
  4. 填入设置页「飞书 Webhook」配置

设计: 失败静默降级, 绝不因推送失败阻断告警主流程 (落盘 / SSE 推送)。
     去重不在本层做, 复用 MonitorRuleEngine 的 cooldown。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time

logger = logging.getLogger(__name__)

# 单次推送最长字符 (飞书单条文本消息上限 30KB, 这里保守截断避免刷屏)
_MAX_LEN = 500

# 卡片消息正文最长字符 (飞书 interactive 卡片上限 30KB, 保守留余量给标题/结构)
_CARD_MAX_LEN = 28000

# 飞书自定义机器人 Webhook 前缀 (用于 URL 合法性校验)
FEISHU_HOOK_PREFIX = "https://open.feishu.cn/open-apis/bot/v2/hook/"


def _truncate(text: str) -> str:
    """截断超长文本。"""
    text = (text or "").strip()
    return text[:_MAX_LEN] + ("…" if len(text) > _MAX_LEN else "")


def is_valid_feishu_url(url: str) -> bool:
    """校验是否为合法的飞书自定义机器人 Webhook 地址。"""
    return bool(url) and url.startswith(FEISHU_HOOK_PREFIX)


def _gen_sign(timestamp: str, secret: str) -> str:
    """计算飞书自定义机器人签名。

    算法 (官方): 把 `timestamp + "\\n" + secret` 作为签名字符串 (key),
    用 HmacSHA256 计算空字符串的签名结果, 再 Base64 编码。
    """
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(
        string_to_sign.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def _truncate_card(text: str) -> str:
    """截断卡片正文 (留余量给标题与卡片结构)。"""
    text = (text or "").strip()
    return text[:_CARD_MAX_LEN] + ("…" if len(text) > _CARD_MAX_LEN else "")


_FEISHU_MAX_ATTEMPTS = 3


def _post_feishu(webhook_url: str, payload: dict, secret: str) -> bool:
    """发送飞书 webhook 请求并判定成败 (供 text / card 共用)。

    成功响应: HTTP 200 且业务 code=0 (或非 JSON/非 dict 的 200)。

    瞬时失败 (网络/超时/HTTP 5xx) 会**带退避重试** —— 告警冷却在事件生成时即打戳,
    一次瞬时 5xx/timeout 若不重试, 该告警会被冷却窗口(默认 1h)压掉, 离屏用户彻底
    收不到推送。永久失败 (4xx / 业务 code≠0, 如签名错、URL 失效) 不重试。最终失败
    记 WARNING (而非之前的 debug), 保证「推送丢了」在日志里可见。
    """
    import httpx

    last_err = ""
    for attempt in range(1, _FEISHU_MAX_ATTEMPTS + 1):
        try:
            # 启用签名校验时, 请求体须带 timestamp + sign (每次重试都重算, 防时间戳过期)
            if secret:
                timestamp = str(int(time.time()))
                payload["timestamp"] = timestamp
                payload["sign"] = _gen_sign(timestamp, secret)

            resp = httpx.post(webhook_url, json=payload, timeout=5.0)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                except ValueError:
                    return True  # 非 JSON 的 200, 视为成功
                if isinstance(data, dict):
                    code = data.get("code", data.get("StatusCode", 0))
                    if code == 0:
                        return True
                    # 业务失败(签名错/格式错等): 重试无益, 直接失败
                    logger.warning("飞书推送业务失败(不重试): %s", data)
                    return False
                return True  # 200 且 JSON 非 dict, 视为成功
            # 4xx 客户端错误(URL 失效等): 不重试; 5xx: 落入重试
            last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            if resp.status_code < 500:
                logger.warning("飞书推送失败(不重试, 客户端错误): %s", last_err)
                return False
        except Exception as e:  # noqa: BLE001 — 网络/超时, 可重试
            last_err = str(e)

        if attempt < _FEISHU_MAX_ATTEMPTS:
            time.sleep(min(2 ** (attempt - 1), 3))  # 退避: 1s, 2s

    logger.warning("飞书 Webhook 推送最终失败(已重试 %d 次): %s", _FEISHU_MAX_ATTEMPTS, last_err)
    return False


def send_feishu(webhook_url: str, title: str, body: str, secret: str = "") -> bool:
    """推送一条文本消息到飞书群机器人。

    Args:
        webhook_url: 飞书自定义机器人 Webhook 地址
        title:       消息标题 (与正文拼接为一条文本)
        body:        消息正文
        secret:      签名密钥 (机器人启用了「签名校验」时必填; 留空则不带签名)

    Returns:
        True=成功送达, False=失败或 URL 非法。
        失败静默, 不抛异常 (Webhook 是辅助通道, 不能阻断告警主流程)。
    """
    if not is_valid_feishu_url(webhook_url):
        return False

    text = _truncate(f"{title}\n{body}".strip())
    if not text:
        return False

    payload: dict = {"msg_type": "text", "content": {"text": text}}
    return _post_feishu(webhook_url, payload, secret)


def send_feishu_card(webhook_url: str, title: str, subtitle: str, body_md: str, secret: str = "") -> bool:
    """推送一条 interactive 卡片消息到飞书群机器人 —— 用 lark_md 渲染完整 markdown 报告。

    飞书「自定义机器人」webhook 不支持文件附件, 但 interactive 卡片的 lark_md 元素
    可渲染 markdown, 能承载完整复盘报告(通常 2-5KB, 远小于卡片 30KB 上限)。

    Args:
        webhook_url: 飞书自定义机器人 Webhook 地址
        title:       卡片标题 (显示在蓝色 header)
        subtitle:    副标题 (加粗显示, 如日期/情绪标签; 留空则省略)
        body_md:     卡片正文 markdown (报告全文)
        secret:      签名密钥 (启用签名校验时必填)

    Returns:
        True=成功送达, False=失败或 URL 非法。
        失败静默, 不抛异常 (与 send_feishu 一致, 不阻断告警主流程)。
    """
    if not is_valid_feishu_url(webhook_url):
        return False

    body = _truncate_card(body_md)
    elements: list[dict] = []
    if subtitle.strip():
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"**{subtitle.strip()}**"},
        })
        elements.append({"tag": "hr"})
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": body},
    })

    payload: dict = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "blue",
            },
            "elements": elements,
        },
    }
    return _post_feishu(webhook_url, payload, secret)
