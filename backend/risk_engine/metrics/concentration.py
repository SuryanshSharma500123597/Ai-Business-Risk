"""Concentration Dimension Metrics (Spec §7 & §17.1).

Pure-function implementations for Herfindahl-Hirschman Index (HHI),
Top-1 Concentration (CR1), and Top-3 Concentration (CR3).
"""

from __future__ import annotations

from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_hhi(shares: list[float] | list[dict[str, Any]]) -> MetricResult:
    if not shares:
        return MetricResult(
            metric_id="hhi",
            name="Herfindahl-Hirschman Index (HHI)",
            dimension="concentration",
            value=0.0,
            status=MetricStatus.VALID,
            message="No concentration buckets reported (dispersed)",
            unit="ratio",
        )

    clean_shares = []
    for item in shares:
        val = (
            item.get("share")
            if isinstance(item, dict)
            else getattr(item, "share", item if isinstance(item, float | int) else None)
        )
        if val is not None and val >= 0:
            clean_shares.append(val)

    if not clean_shares:
        return MetricResult(
            metric_id="hhi",
            name="Herfindahl-Hirschman Index (HHI)",
            dimension="concentration",
            value=0.0,
            status=MetricStatus.VALID,
            unit="ratio",
        )

    hhi_val = sum(s**2 for s in clean_shares)
    return MetricResult(
        metric_id="hhi",
        name="Herfindahl-Hirschman Index (HHI)",
        dimension="concentration",
        value=hhi_val,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"share_count": len(clean_shares)},
    )


def calc_cr1(shares: list[float] | list[dict[str, Any]]) -> MetricResult:
    if not shares:
        return MetricResult(
            metric_id="cr1",
            name="Top-1 Concentration (CR1)",
            dimension="concentration",
            value=0.0,
            status=MetricStatus.VALID,
            unit="ratio",
        )

    clean_shares = []
    for item in shares:
        val = (
            item.get("share")
            if isinstance(item, dict)
            else getattr(item, "share", item if isinstance(item, float | int) else None)
        )
        if val is not None and val >= 0:
            clean_shares.append(val)

    if not clean_shares:
        return MetricResult(
            metric_id="cr1",
            name="Top-1 Concentration (CR1)",
            dimension="concentration",
            value=0.0,
            status=MetricStatus.VALID,
            unit="ratio",
        )

    cr1_val = max(clean_shares)
    return MetricResult(
        metric_id="cr1",
        name="Top-1 Concentration (CR1)",
        dimension="concentration",
        value=cr1_val,
        status=MetricStatus.VALID,
        unit="ratio",
    )


def calc_cr3(shares: list[float] | list[dict[str, Any]]) -> MetricResult:
    if not shares:
        return MetricResult(
            metric_id="cr3",
            name="Top-3 Concentration (CR3)",
            dimension="concentration",
            value=0.0,
            status=MetricStatus.VALID,
            unit="ratio",
        )

    clean_shares = []
    for item in shares:
        val = (
            item.get("share")
            if isinstance(item, dict)
            else getattr(item, "share", item if isinstance(item, float | int) else None)
        )
        if val is not None and val >= 0:
            clean_shares.append(val)

    sorted_shares = sorted(clean_shares, reverse=True)
    cr3_val = min(1.0, sum(sorted_shares[:3]))

    return MetricResult(
        metric_id="cr3",
        name="Top-3 Concentration (CR3)",
        dimension="concentration",
        value=cr3_val,
        status=MetricStatus.VALID,
        unit="ratio",
    )
