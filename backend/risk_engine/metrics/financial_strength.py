"""Financial Strength Dimension Metrics (Spec §2 & §17.1).

Pure-function implementations for profitability, leverage, and coverage ratios.
"""

from __future__ import annotations

from typing import Any

from backend.risk_engine.contracts import MetricResult, MetricStatus


def calc_gross_margin(period: dict[str, Any]) -> MetricResult:
    revenue = period.get("revenue")
    gp = period.get("gross_profit")
    cogs = period.get("cogs")

    if gp is None and revenue is not None and cogs is not None:
        gp = revenue - cogs

    if revenue is None or gp is None:
        return MetricResult(
            metric_id="gross_margin",
            name="Gross Margin",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing revenue or gross_profit",
            unit="percent",
        )

    if revenue <= 0:
        return MetricResult(
            metric_id="gross_margin",
            name="Gross Margin",
            dimension="financial_strength",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="Revenue is zero or negative",
            forced_score=100.0,
            unit="percent",
        )

    margin_pct = (gp / revenue) * 100.0
    return MetricResult(
        metric_id="gross_margin",
        name="Gross Margin",
        dimension="financial_strength",
        value=margin_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"revenue": revenue, "gross_profit": gp},
    )


def calc_operating_margin(period: dict[str, Any]) -> MetricResult:
    revenue = period.get("revenue")
    ebit = period.get("ebit")

    if revenue is None or ebit is None:
        return MetricResult(
            metric_id="operating_margin",
            name="Operating Margin",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing revenue or ebit",
            unit="percent",
        )

    if revenue <= 0:
        return MetricResult(
            metric_id="operating_margin",
            name="Operating Margin",
            dimension="financial_strength",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="Revenue is zero or negative",
            forced_score=100.0,
            unit="percent",
        )

    margin_pct = (ebit / revenue) * 100.0
    return MetricResult(
        metric_id="operating_margin",
        name="Operating Margin",
        dimension="financial_strength",
        value=margin_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"revenue": revenue, "ebit": ebit},
    )


def calc_net_margin(period: dict[str, Any]) -> MetricResult:
    revenue = period.get("revenue")
    net_income = period.get("net_income")

    if revenue is None or net_income is None:
        return MetricResult(
            metric_id="net_margin",
            name="Net Margin",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing revenue or net_income",
            unit="percent",
        )

    if revenue <= 0:
        return MetricResult(
            metric_id="net_margin",
            name="Net Margin",
            dimension="financial_strength",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="Revenue is zero or negative",
            forced_score=100.0,
            unit="percent",
        )

    margin_pct = (net_income / revenue) * 100.0
    return MetricResult(
        metric_id="net_margin",
        name="Net Margin",
        dimension="financial_strength",
        value=margin_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"revenue": revenue, "net_income": net_income},
    )


def calc_roa(period: dict[str, Any]) -> MetricResult:
    net_income = period.get("net_income")
    total_assets = period.get("total_assets")

    if net_income is None or total_assets is None:
        return MetricResult(
            metric_id="roa",
            name="Return on Assets (ROA)",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing net_income or total_assets",
            unit="percent",
        )

    if total_assets <= 0:
        return MetricResult(
            metric_id="roa",
            name="Return on Assets (ROA)",
            dimension="financial_strength",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="Total assets is zero or negative",
            forced_score=100.0,
            unit="percent",
        )

    roa_pct = (net_income / total_assets) * 100.0
    return MetricResult(
        metric_id="roa",
        name="Return on Assets (ROA)",
        dimension="financial_strength",
        value=roa_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"net_income": net_income, "total_assets": total_assets},
    )


def calc_roe(period: dict[str, Any]) -> MetricResult:
    net_income = period.get("net_income")
    equity = period.get("equity")

    if net_income is None or equity is None:
        return MetricResult(
            metric_id="roe",
            name="Return on Equity (ROE)",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing net_income or equity",
            unit="percent",
        )

    if equity <= 0:
        return MetricResult(
            metric_id="roe",
            name="Return on Equity (ROE)",
            dimension="financial_strength",
            value=0.0,
            status=MetricStatus.FLAGGED,
            message="Equity is zero or negative",
            forced_score=100.0,
            unit="percent",
        )

    roe_pct = (net_income / equity) * 100.0
    return MetricResult(
        metric_id="roe",
        name="Return on Equity (ROE)",
        dimension="financial_strength",
        value=roe_pct,
        status=MetricStatus.VALID,
        unit="percent",
        inputs_used={"net_income": net_income, "equity": equity},
    )


def calc_debt_to_equity(period: dict[str, Any]) -> MetricResult:
    total_debt = period.get("total_debt")
    equity = period.get("equity")
    st_debt = period.get("st_debt")
    lt_debt = period.get("lt_debt")

    if total_debt is None and (st_debt is not None or lt_debt is not None):
        total_debt = (st_debt or 0.0) + (lt_debt or 0.0)

    if total_debt is None or equity is None:
        return MetricResult(
            metric_id="debt_to_equity",
            name="Debt to Equity Ratio",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing total_debt or equity",
            unit="ratio",
        )

    if equity <= 0:
        # Ratio is undefined (division by non-positive equity). The frozen spec maps
        # this edge case straight to the worst band, so report no fabricated ratio and
        # apply the score directly. Emitting float("inf") here previously raised a
        # MetricResult validation error and crashed evaluation of distressed companies.
        return MetricResult(
            metric_id="debt_to_equity",
            name="Debt to Equity Ratio",
            dimension="financial_strength",
            value=None,
            status=MetricStatus.FLAGGED,
            message="Equity is zero or negative (undefined ratio)",
            forced_score=100.0,
            unit="ratio",
            inputs_used={"total_debt": total_debt, "equity": equity},
        )

    ratio = total_debt / equity
    return MetricResult(
        metric_id="debt_to_equity",
        name="Debt to Equity Ratio",
        dimension="financial_strength",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"total_debt": total_debt, "equity": equity},
    )


def calc_debt_to_ebitda(period: dict[str, Any]) -> MetricResult:
    total_debt = period.get("total_debt")
    ebitda = period.get("ebitda")
    st_debt = period.get("st_debt")
    lt_debt = period.get("lt_debt")

    if total_debt is None and (st_debt is not None or lt_debt is not None):
        total_debt = (st_debt or 0.0) + (lt_debt or 0.0)

    if total_debt is None or ebitda is None:
        return MetricResult(
            metric_id="debt_to_ebitda",
            name="Debt to EBITDA Ratio",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing total_debt or ebitda",
            unit="ratio",
        )

    if ebitda <= 0:
        # Ratio is undefined (division by non-positive EBITDA); frozen spec maps this
        # edge case to the worst band. See calc_debt_to_equity for why no inf is emitted.
        return MetricResult(
            metric_id="debt_to_ebitda",
            name="Debt to EBITDA Ratio",
            dimension="financial_strength",
            value=None,
            status=MetricStatus.FLAGGED,
            message="EBITDA is zero or negative (undefined ratio)",
            forced_score=100.0,
            unit="ratio",
            inputs_used={"total_debt": total_debt, "ebitda": ebitda},
        )

    ratio = total_debt / ebitda
    return MetricResult(
        metric_id="debt_to_ebitda",
        name="Debt to EBITDA Ratio",
        dimension="financial_strength",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"total_debt": total_debt, "ebitda": ebitda},
    )


def calc_interest_coverage(period: dict[str, Any]) -> MetricResult:
    ebit = period.get("ebit")
    interest = period.get("interest_expense")

    if ebit is None or interest is None:
        return MetricResult(
            metric_id="interest_coverage",
            name="Interest Coverage Ratio",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing ebit or interest_expense",
            unit="ratio",
        )

    if interest <= 0:
        # Zero or no interest expense -> highly covered / unconstrained
        return MetricResult(
            metric_id="interest_coverage",
            name="Interest Coverage Ratio",
            dimension="financial_strength",
            value=999.0,
            status=MetricStatus.VALID,
            message="Zero interest expense",
            unit="ratio",
        )

    ratio = ebit / interest
    return MetricResult(
        metric_id="interest_coverage",
        name="Interest Coverage Ratio",
        dimension="financial_strength",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"ebit": ebit, "interest_expense": interest},
    )


def calc_dscr(period: dict[str, Any]) -> MetricResult:
    ebitda = period.get("ebitda")
    interest = period.get("interest_expense") or 0.0
    st_debt = period.get("st_debt") or 0.0

    if ebitda is None:
        return MetricResult(
            metric_id="dscr",
            name="Debt Service Coverage Ratio (DSCR)",
            dimension="financial_strength",
            status=MetricStatus.MISSING_INPUT,
            message="Missing ebitda",
            unit="ratio",
        )

    debt_service = interest + st_debt
    if debt_service <= 0:
        return MetricResult(
            metric_id="dscr",
            name="Debt Service Coverage Ratio (DSCR)",
            dimension="financial_strength",
            value=999.0,
            status=MetricStatus.VALID,
            message="Zero debt service obligation",
            unit="ratio",
        )

    ratio = ebitda / debt_service
    return MetricResult(
        metric_id="dscr",
        name="Debt Service Coverage Ratio (DSCR)",
        dimension="financial_strength",
        value=ratio,
        status=MetricStatus.VALID,
        unit="ratio",
        inputs_used={"ebitda": ebitda, "debt_service": debt_service},
    )
