#!/usr/bin/env python3
"""Generate a deterministic canonical company JSON document (no database writes)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company


def _json_value(value: str) -> Any:
    candidate = Path(value)
    text = candidate.read_text(encoding="utf-8") if candidate.is_file() else value
    return json.loads(text)


def _json_config(value: str) -> dict[str, Any]:
    payload = _json_value(value)
    if not isinstance(payload, dict):
        raise ValueError("config JSON must be an object")
    return payload


def build_config(args: argparse.Namespace) -> SyntheticCompanyConfig:
    values: dict[str, Any] = _json_config(args.config) if args.config else {}
    for name in ("sector", "size", "health", "currency", "frequency"):
        value = getattr(args, name)
        if value is not None:
            values[name] = value
    if args.periods is not None:
        values["periods"] = args.periods
    if args.seed is not None:
        values["seed"] = args.seed
    if args.anomalies is not None:
        values["inject_anomalies"] = _json_value(args.anomalies)
        if not isinstance(values["inject_anomalies"], list):
            raise ValueError("anomalies JSON must be an array")
    if "seed" not in values:
        raise ValueError("--seed or seed in --config is required")
    return SyntheticCompanyConfig.model_validate(values)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", help="JSON object or JSON file with generator settings")
    result.add_argument("--sector", choices=["manufacturing", "retail", "services_saas"])
    result.add_argument("--size", choices=["small", "medium", "large"])
    result.add_argument("--health", choices=["healthy", "stable", "stressed"])
    result.add_argument("--currency", choices=["INR", "USD", "EUR"])
    result.add_argument("--frequency", choices=["monthly", "quarterly", "annual"])
    result.add_argument("--periods", type=int)
    result.add_argument("--seed", type=int)
    result.add_argument("--anomalies", help="anomaly JSON array or file")
    result.add_argument("--output", type=Path, default=Path("company.json"))
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        config = build_config(args)
        company = generate_company(config)
        args.output.write_text(
            json.dumps(company.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
        )
        print(f"generated {len(company.periods)} periods to {args.output}")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"generation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
