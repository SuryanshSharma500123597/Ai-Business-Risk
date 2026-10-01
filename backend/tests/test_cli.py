from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_company import main as generate_main
from scripts.seed_db import main as seed_main


def test_generate_cli_supports_json_options(tmp_path: Path) -> None:
    output = tmp_path / "company.json"
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"seed": 1234, "periods": 12, "sector": "retail"}), encoding="utf-8"
    )
    assert (
        generate_main(["--config", str(config), "--health", "healthy", "--output", str(output)])
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["generator_config"]["seed"] == 1234
    assert len(payload["periods"]) == 12


def test_generate_cli_supports_anomaly_file(tmp_path: Path) -> None:
    anomalies = tmp_path / "anomalies.json"
    output = tmp_path / "company.json"
    anomalies.write_text(
        json.dumps(
            [{"type": "margin_collapse", "start_month": 5, "duration_months": 2, "magnitude": 0.5}]
        ),
        encoding="utf-8",
    )
    assert (
        generate_main(["--seed", "1236", "--anomalies", str(anomalies), "--output", str(output)])
        == 0
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["generator_config"]["inject_anomalies"][0]["type"] == "margin_collapse"


def test_seed_cli_migrates_and_persists_without_create_all(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_path = tmp_path / "company.json"
    database = tmp_path / "seed.db"
    assert generate_main(["--seed", "1235", "--periods", "12", "--output", str(input_path)]) == 0
    assert seed_main([str(input_path), "--database-url", f"sqlite:///{database}"]) == 0
    output = capsys.readouterr().out
    assert "seeded company" in output
    assert database.exists()
