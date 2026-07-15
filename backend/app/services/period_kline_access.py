"""月/年 K 访问权限（TickFlow 不提供，仅插件源如 stock-sdk）。"""
from __future__ import annotations


def _provider_has(dataset: str, provider: str) -> bool:
    if provider == "tickflow":
        return False
    from app.data_providers import custom as custom_sources

    return custom_sources.provider_has_dataset(provider, dataset)


def period_provider_active(dataset: str) -> bool:
    from app.services import preferences

    if dataset == "monthly":
        provider = preferences.get_monthly_data_provider()
    elif dataset == "yearly":
        provider = preferences.get_yearly_data_provider()
    else:
        return False
    if provider == "tickflow":
        return False
    return _provider_has(dataset, provider)


def monthly_access_flags(capset) -> dict:  # noqa: ARG001
    from app.services import preferences

    active = period_provider_active("monthly")
    return {
        "monthly_access": active,
        "monthly_provider": preferences.get_monthly_data_provider(),
        "monthly_provider_active": active,
    }


def yearly_access_flags(capset) -> dict:  # noqa: ARG001
    from app.services import preferences

    active = period_provider_active("yearly")
    return {
        "yearly_access": active,
        "yearly_provider": preferences.get_yearly_data_provider(),
        "yearly_provider_active": active,
    }
