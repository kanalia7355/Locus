import yaml

from loop_engine.config import default, load
from loop_engine.schemas import validate


def test_config_schema_accepts_opencode_executor(tmp_path) -> None:
    config = default()
    config["security"]["sandbox_executor"] = "opencode"
    config["security"]["allow_model_execution"] = True
    config["opencode"]["model"] = "opencode/iceman-free"
    validate("config", config)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    loaded = load(path)
    assert loaded["security"]["sandbox_executor"] == "opencode"
    assert loaded["opencode"]["model"] == "opencode/iceman-free"


def test_existing_default_config_still_valid() -> None:
    config = default()
    validate("config", config)
    assert config["security"]["sandbox_executor"] == "unavailable"
