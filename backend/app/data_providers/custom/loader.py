"""Load custom data source definitions from user data files."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

from app.config import settings
from app.data_providers.custom.config import CustomSourceConfig, load_config
from app.data_providers.custom.provider import GenericHTTPProvider

logger = logging.getLogger(__name__)

_PROVIDERS: dict[str, GenericHTTPProvider] = {}
_LOAD_ERRORS: list[dict] = []

_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# 内置(非 YAML)扩展数据源。它们与 tickflow 一样是代码内置, 但复用本注册表以让
# services 的「非 tickflow → custom_sources」分流点零改动即可路由过去。
# 这些名字不出现在「自定义源」列表, 也不可通过 save/delete/get_config 编辑。
_BUILTIN_NAMES = {"stocksdk"}


def _register_builtins() -> None:
    """把内置扩展 provider 注入注册表(每次 load_all 后重建)。缺依赖也注册, 抓取时才报错。"""
    try:
        from app.data_providers.stocksdk import StockSDKProvider

        _PROVIDERS["stocksdk"] = StockSDKProvider()  # type: ignore[assignment]
    except Exception as e:  # noqa: BLE001
        logger.warning("stocksdk 内置数据源注册失败: %s", e)


def data_sources_dir() -> Path:
    return settings.data_dir / "data_sources"


def load_all(path: Path | None = None) -> None:
    """Load all custom provider YAML files into process memory."""
    global _PROVIDERS, _LOAD_ERRORS
    for provider in _PROVIDERS.values():
        provider.close()
    _PROVIDERS = {}
    _LOAD_ERRORS = []

    base = path or data_sources_dir()
    base.mkdir(parents=True, exist_ok=True)
    for file in sorted([*base.glob("*.yaml"), *base.glob("*.yml")]):
        try:
            config = load_config(file)
            provider = GenericHTTPProvider(config)
            errors = provider.validate()
            if errors:
                _LOAD_ERRORS.append({"path": str(file), "name": config.name, "errors": errors})
                provider.close()
                continue
            _PROVIDERS[config.name] = provider
        except Exception as e:  # noqa: BLE001
            logger.warning("custom data source load failed %s: %s", file, e)
            _LOAD_ERRORS.append({"path": str(file), "errors": [str(e)]})

    _register_builtins()


def list_sources() -> list[dict]:
    """只列出用户自定义(YAML)源, 内置扩展(stocksdk 等)由各自的 builtin 通道呈现。"""
    return [
        {
            "name": provider.name,
            "display_name": provider.config.display_name,
            "datasets": sorted(provider.config.datasets.keys()),
            "path": str(provider.config.path) if provider.config.path else None,
        }
        for provider in _PROVIDERS.values()
        if not getattr(provider, "builtin", False)
    ]


def is_builtin(name: str) -> bool:
    return (name or "").lower() in _BUILTIN_NAMES


def names() -> set[str]:
    return set(_PROVIDERS)


def errors() -> list[dict]:
    return list(_LOAD_ERRORS)


def get_provider(name: str) -> GenericHTTPProvider:
    provider = _PROVIDERS.get((name or "").lower())
    if provider is None:
        raise ValueError(f"Custom data source not found or invalid: {name}")
    return provider


def is_custom_provider(name: str) -> bool:
    return (name or "").lower() in _PROVIDERS


def provider_has_dataset(name: str, dataset: str) -> bool:
    """判断某个 custom 源是否配置了指定数据集。

    用于主流程分流: 总开关选了 custom, 但某个数据集未启用时, 该数据集回退 TickFlow。
    """
    provider = _PROVIDERS.get((name or "").lower())
    if provider is None:
        return False
    return dataset in provider.config.datasets


def get_config_dict(name: str) -> dict | None:
    """读取一个已加载 custom 源的原始配置 dict(用于前端编辑回填)。内置源不可编辑, 返回 None。"""
    if is_builtin(name):
        return None
    provider = _PROVIDERS.get((name or "").lower())
    if provider is None:
        return None
    return _config_to_dict(provider.config)


def _config_to_dict(config: CustomSourceConfig) -> dict:
    auth = config.auth
    out: dict = {
        "name": config.name,
        "display_name": config.display_name,
        "auth": {
            "type": auth.type,
            **({"token_env": auth.token_env} if auth.token_env else {}),
            **({"header": auth.header} if auth.type in {"bearer", "header"} and auth.header != "Authorization" else {}),
            **({"param": auth.param} if auth.type == "query" and auth.param != "token" else {}),
        },
        "datasets": {},
    }
    for ds_name, ds in config.datasets.items():
        out["datasets"][ds_name] = {
            "url": ds.url,
            "method": ds.method,
            **({"batch": ds.batch} if ds.batch is not None else {}),
            **({"rpm": ds.rpm} if ds.rpm is not None else {}),
            "response_path": ds.response_path,
            "field_map": dict(ds.field_map),
            **({"transforms": dict(ds.transforms)} if ds.transforms else {}),
            "symbols_param": ds.symbols_param,
            "start_param": ds.start_param,
            "end_param": ds.end_param,
        }
    return out


def save_config(name: str, config: dict) -> Path:
    """把一份配置 dict 写成 data/data_sources/{name}.yaml, 返回写入路径。"""
    if is_builtin(name):
        raise ValueError(f"'{name}' 是内置数据源, 不可编辑")
    if not _NAME_RE.match(name or ""):
        raise ValueError(f"invalid data source name: {name!r} (only lowercase a-z 0-9 _ allowed)")
    base = data_sources_dir()
    base.mkdir(parents=True, exist_ok=True)
    path = (base / f"{name}.yaml").resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("invalid data source name: path escape detected")
    cleaned = _sanitize_for_yaml(config)
    path.write_text(yaml.safe_dump(cleaned, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def delete_config(name: str) -> bool:
    """删除 data/data_sources/{name}.yaml。返回是否真的删除了。"""
    if is_builtin(name):
        raise ValueError(f"'{name}' 是内置数据源, 不可删除")
    if not _NAME_RE.match(name or ""):
        raise ValueError(f"invalid data source name: {name!r}")
    base = data_sources_dir().resolve()
    path = (base / f"{name}.yaml").resolve()
    if not path.is_relative_to(base):
        raise ValueError("invalid data source name: path escape detected")
    if not path.exists():
        return False
    path.unlink()
    return True


def _sanitize_for_yaml(config: dict) -> dict:
    """剔除前端可能塞进来的空值/未启用数据集, 保证写入的 yaml 干净。"""
    out: dict = {
        "name": str(config.get("name", "")).lower(),
        "display_name": str(config.get("display_name") or config.get("name", "")),
    }
    auth_raw = config.get("auth") or {}
    auth_type = str(auth_raw.get("type", "none") or "none").lower()
    auth: dict = {"type": auth_type}
    if auth_type != "none" and auth_raw.get("token_env"):
        auth["token_env"] = str(auth_raw["token_env"])
        if auth_type in {"bearer", "header"} and auth_raw.get("header"):
            auth["header"] = str(auth_raw["header"])
        if auth_type == "query" and auth_raw.get("param"):
            auth["param"] = str(auth_raw["param"])
    out["auth"] = auth

    datasets_out: dict = {}
    for ds_name, ds_cfg in (config.get("datasets") or {}).items():
        if ds_name not in {"daily", "adj_factor", "realtime", "minute", "financial"}:
            continue
        if not isinstance(ds_cfg, dict):
            continue
        ds = _sanitize_dataset(ds_cfg)
        if ds:
            datasets_out[ds_name] = ds
    out["datasets"] = datasets_out
    return out


def _sanitize_dataset(ds_cfg: dict) -> dict:
    out: dict = {}
    url = str(ds_cfg.get("url", "") or "").strip()
    if not url:
        return out
    out["url"] = url
    method = str(ds_cfg.get("method", "GET") or "GET").upper()
    out["method"] = method
    if ds_cfg.get("batch") is not None:
        try:
            out["batch"] = int(ds_cfg["batch"])
        except (TypeError, ValueError):
            pass
    if ds_cfg.get("rpm") is not None:
        try:
            out["rpm"] = int(ds_cfg["rpm"])
        except (TypeError, ValueError):
            pass
    out["response_path"] = str(ds_cfg.get("response_path", "") or "")
    field_map = {
        str(k): str(v)
        for k, v in (ds_cfg.get("field_map") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if field_map:
        out["field_map"] = field_map
    transforms = {
        str(k): str(v)
        for k, v in (ds_cfg.get("transforms") or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if transforms:
        out["transforms"] = transforms
    if ds_cfg.get("symbols_param"):
        out["symbols_param"] = str(ds_cfg["symbols_param"])
    if ds_cfg.get("start_param"):
        out["start_param"] = str(ds_cfg["start_param"])
    if ds_cfg.get("end_param"):
        out["end_param"] = str(ds_cfg["end_param"])
    return out


# 导入时即注册内置源, 保证 names()/get_provider() 在 startup load_all 之前也可用。
_register_builtins()

