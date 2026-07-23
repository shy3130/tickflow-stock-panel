from app.api.settings import DatasetConfigIn
from app.data_providers.custom.config import CustomSourceConfig, _dataset_from_dict
from app.data_providers.custom.loader import _config_to_dict, _sanitize_for_yaml


def test_minute_request_parameter_names_survive_config_round_trip():
    dataset = DatasetConfigIn(
        url="https://example.test/minute",
        method="GET",
        asset_type_param="asset",
        freq_param="period",
    ).model_dump()

    cleaned = _sanitize_for_yaml({
        "name": "test_source",
        "display_name": "Test Source",
        "datasets": {"minute": dataset},
    })
    parsed = _dataset_from_dict(cleaned["datasets"]["minute"])
    exposed = _config_to_dict(CustomSourceConfig(
        name="test_source",
        display_name="Test Source",
        datasets={"minute": parsed},
    ))

    assert parsed.asset_type_param == "asset"
    assert parsed.freq_param == "period"
    assert exposed["datasets"]["minute"]["asset_type_param"] == "asset"
    assert exposed["datasets"]["minute"]["freq_param"] == "period"


def test_timeout_survives_config_round_trip():
    """timeout 必须在 UI 保存往返中保留 (核心修复), 且默认 30 不污染 YAML。"""
    dataset = DatasetConfigIn(
        url="https://example.test/daily",
        method="POST",
        timeout=120.0,
    ).model_dump()

    cleaned = _sanitize_for_yaml({
        "name": "test_source",
        "display_name": "Test Source",
        "datasets": {"daily": dataset},
    })
    parsed = _dataset_from_dict(cleaned["datasets"]["daily"])
    exposed = _config_to_dict(CustomSourceConfig(
        name="test_source",
        display_name="Test Source",
        datasets={"daily": parsed},
    ))

    assert parsed.timeout == 120.0
    assert exposed["datasets"]["daily"]["timeout"] == 120.0

    # 默认 30 不 emit, 保持 YAML 干净
    default_dataset = DatasetConfigIn(url="https://example.test/realtime", method="GET").model_dump()
    cleaned2 = _sanitize_for_yaml({
        "name": "test_source",
        "display_name": "Test Source",
        "datasets": {"realtime": default_dataset},
    })
    parsed2 = _dataset_from_dict(cleaned2["datasets"]["realtime"])
    exposed2 = _config_to_dict(CustomSourceConfig(
        name="test_source",
        display_name="Test Source",
        datasets={"realtime": parsed2},
    ))
    assert parsed2.timeout == 30.0
    assert "timeout" not in exposed2["datasets"]["realtime"]
