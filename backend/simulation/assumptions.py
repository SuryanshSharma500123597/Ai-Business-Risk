"""Twin parameter derivation from history (Phase 6, frozen simulation.md §1).

Every parameter in the frozen §1 table is either derived from the trailing
12-month window of ``PeriodFinancials`` ([R] real) or is a documented default
([A] assumption). Nothing here invents a value silently: each derivation
records the parameter, its tag, the rule that produced it, and whether a
documented fallback fired, so a reader can always separate a measured input
from an assumed one.

No I/O, no network, no LLM, no database (architecture rule R3).
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.data_engine.contracts import CompanyDataset, PeriodFinancials
from backend.simulation.contracts import (
    DEBT_BUCKETS,
    MIN_TRAILING_MONTHS,
    TRAILING_WINDOW,
    AssumptionRecord,
    DebtAmortization,
    ParameterTag,
    SimulationAssumptions,
    SimulationStatus,
)

# --- frozen §1 defaults, clamps and fallbacks ------------------------------
GROWTH_RATE_CLAMP = (-0.05, 0.15)  # g: trailing 12-mo CAGR clamped [-5%, +15%]
TAX_RATE_CLAMP = (0.05, 0.35)  # tau: effective rate clamped [5%, 35%]
TAX_RATE_FALLBACK = 0.25  # tau offline fallback
BASE_RATE_FALLBACK = 0.06  # r0 offline fallback (6%)
FALLBACK_FX_SHARE = 0.1  # kappa_fx / rho_rev offline fallback
FALLBACK_COMMODITY_SHARE = 0.2  # kappa_c offline fallback
FALLBACK_FLOATING_SHARE = 0.5  # phi offline fallback
PASS_THROUGH = 0.3  # ptc, "shared with risk engine" (risk_engine/metrics/market.py)
FX_DEMAND_ELASTICITY = 0.5  # e_fx
OPEX_BUFFER_MULTIPLE = 1.0  # B = 1.0 x monthly opex
OPEX_REVOLVER_MULTIPLE = 3.0  # RC = 3.0 x monthly opex
DAYS_IN_MONTH = 30.0  # §1 uses a 30-day month for DSO/DIO/DPO
# Denominator guard for the two-parameter opex regression. Below this the
# design matrix is numerically singular and the documented fallback is used.
_OLS_SINGULAR_TOLERANCE = 1e-12


class InsufficientHistoryError(ValueError):
    """Raised when history cannot support the frozen 12-month derivations.

    simulation.md §1 fixes every derivation to a trailing 12-month window.
    With fewer periods the specification cannot be honoured, and shortening the
    window silently would fabricate inputs, so the run refuses to start.
    """

    status = SimulationStatus.INSUFFICIENT_HISTORY


def derive_assumptions(
    dataset: CompanyDataset,
) -> tuple[SimulationAssumptions, list[AssumptionRecord], list[str]]:
    """Derive the full §1 parameter set from a company dataset.

    Returns the assumptions, one record per parameter, and the names of
    parameters whose documented fallback had to be used.
    """
    periods = dataset.periods
    if len(periods) < MIN_TRAILING_MONTHS:
        raise InsufficientHistoryError(
            f"twin derivation needs >= {MIN_TRAILING_MONTHS} monthly periods "
            f"(simulation.md §1 trailing-window rules); got {len(periods)}. "
            "Annual and quarterly sources are not monthlyized by Phase 6."
        )

    window: list[PeriodFinancials] = list(periods[-TRAILING_WINDOW:])
    latest = periods[-1]
    records: list[AssumptionRecord] = []
    derived: dict[str, float] = {}

    def record(
        parameter: str,
        value: float,
        tag: ParameterTag,
        source: str,
        fallback: bool = False,
    ) -> float:
        derived[parameter] = value
        records.append(
            AssumptionRecord(
                parameter=parameter,
                value=value,
                tag=tag,
                source=source,
                fallback_used=fallback,
            )
        )
        return value

    revenue = require_series(window, "revenue")
    cogs = require_series(window, "cogs")
    opex = require_series(window, "opex")
    monthly_opex = mean(opex)

    g = derive_growth(revenue)
    record(
        "growth_rate",
        clamp(g, *GROWTH_RATE_CLAMP),
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo revenue CAGR, clamped to {GROWTH_RATE_CLAMP}",
        not is_usable_growth(revenue),
    )
    record(
        "cogs_ratio",
        clamp(mean(safe_ratio(cogs, revenue)), 0.0, 1.0),
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo mean of cogs/revenue",
    )

    fixed, variable, opex_fb = derive_opex_split(opex, revenue)
    opex_src = "OLS of opex on revenue over the trailing window"
    if opex_fb:
        opex_src += "; frozen fallback F=0.5*opex0, v=0.5*opex0/rev0"
    record("fixed_cost", fixed, ParameterTag.ASSUMPTION, opex_src, opex_fb)
    record("variable_cost_ratio", variable, ParameterTag.ASSUMPTION, opex_src, opex_fb)

    da_monthly, da_fb = derive_da(optional_series(window, "da"))
    record(
        "da_monthly",
        da_monthly,
        ParameterTag.REAL,
        "trailing da / 12 (monthly periods already carry monthly D&A)",
        da_fb,
    )

    tax_fb = not has_effective_tax(window)
    record(
        "tax_rate",
        TAX_RATE_FALLBACK if tax_fb else clamp(derive_tax_rate(window), *TAX_RATE_CLAMP),
        ParameterTag.REAL,
        f"effective tax rate from history, clamped to {TAX_RATE_CLAMP}; "
        f"fallback {TAX_RATE_FALLBACK}",
        tax_fb,
    )
    record(
        "base_rate",
        BASE_RATE_FALLBACK,
        ParameterTag.ASSUMPTION,
        "r0 = FEDFUNDS latest + 200bp spread, offline fallback 6% "
        "(simulation.md §1); the twin never fetches, so the fallback is used",
        True,
    )

    phi, phi_fb = derive_floating_share(latest)
    record(
        "floating_debt_share", phi, ParameterTag.REAL, "rate_exposure.floating_debt_share", phi_fb
    )
    kappa_fx, rho_rev, fx_fb = derive_fx_shares(latest)
    record(
        "fx_import_cost_share", kappa_fx, ParameterTag.REAL, "fx_exposure.import_cost_share", fx_fb
    )
    record(
        "fx_revenue_share", rho_rev, ParameterTag.REAL, "fx_exposure.foreign_revenue_share", fx_fb
    )
    kappa_c, comm_fb = derive_commodity_share(latest)
    record(
        "commodity_cost_share", kappa_c, ParameterTag.REAL, "commodity_exposure.cost_share", comm_fb
    )

    dso, dso_fb = derive_wc_days(window, "receivables", revenue)
    record(
        "dso",
        dso,
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo mean receivables/revenue*{DAYS_IN_MONTH:.0f}",
        dso_fb,
    )
    dio, dio_fb = derive_wc_days(window, "inventory", cogs)
    record(
        "dio",
        dio,
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo mean inventory/cogs*{DAYS_IN_MONTH:.0f}",
        dio_fb,
    )
    dpo, dpo_fb = derive_wc_days(window, "payables", cogs)
    record(
        "dpo",
        dpo,
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo mean payables/cogs*{DAYS_IN_MONTH:.0f}",
        dpo_fb,
    )

    capex_monthly, capex_fb = derive_capex(optional_series(window, "capex"))
    record(
        "capex_monthly",
        capex_monthly,
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo mean capex",
        capex_fb,
    )
    record(
        "revenue_capacity",
        max(revenue),
        ParameterTag.REAL,
        f"trailing {TRAILING_WINDOW}-mo max revenue (Capacity0, supply ceiling)",
    )
    record(
        "min_cash_buffer",
        OPEX_BUFFER_MULTIPLE * monthly_opex,
        ParameterTag.ASSUMPTION,
        "B = 1.0 x monthly opex",
    )
    record(
        "revolver_cap",
        OPEX_REVOLVER_MULTIPLE * monthly_opex,
        ParameterTag.ASSUMPTION,
        "RC = 3.0 x monthly opex (must be >= B)",
    )
    record(
        "pass_through", PASS_THROUGH, ParameterTag.ASSUMPTION, "ptc = 0.3, shared with risk_engine"
    )
    record("fx_demand_elasticity", FX_DEMAND_ELASTICITY, ParameterTag.ASSUMPTION, "e_fx = 0.5")

    debt, debt_fb = derive_initial_debt(latest)
    record("initial_debt", debt, ParameterTag.REAL, "D0 = total_debt of the latest period", debt_fb)

    assumptions = SimulationAssumptions(
        **{name: value for name, value in derived.items() if name != "initial_debt"},
        initial_debt=debt,
        debt_amortization=build_amortization(latest),
    )
    return assumptions, records, [r.parameter for r in records if r.fallback_used]


# --- series helpers --------------------------------------------------------


def require_series(periods: Sequence[PeriodFinancials], field: str) -> list[float]:
    """Every value of ``field`` across ``periods``, or refuse to continue.

    A gap in a required series is never zero-filled or forward-filled: it is
    reported, so the caller fails loudly instead of simulating invented data.
    """
    values: list[float] = []
    for period in periods:
        value = getattr(period, field)
        if value is None:
            raise ValueError(
                f"twin derivation requires '{field}' for every trailing period; "
                f"missing in period ending {period.period_end}"
            )
        values.append(float(value))
    return values


def optional_series(periods: Sequence[PeriodFinancials], field: str) -> list[float]:
    """Present values of ``field``; an absent optional series stays empty."""
    return [float(v) for v in (getattr(p, field) for p in periods) if v is not None]


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def safe_ratio(numerator: Sequence[float], denominator: Sequence[float]) -> list[float]:
    """Element-wise ratio where the denominator is non-zero, else 0.0.

    A zero-revenue month cannot yield a meaningful ratio; substituting 0.0 for
    that single month is the standard trailing-mean convention, and the
    resulting mean stays inside the frozen [0,1] clamp for c0.
    """
    return [n / d if d else 0.0 for n, d in zip(numerator, denominator, strict=True)]


def derive_growth(revenue: Sequence[float]) -> float:
    """Annualised revenue growth ``g`` over the trailing window.

    simulation.md §1: "trailing 12-mo revenue CAGR". With monthly periods the
    CAGR is the compounded monthly rate raised to the 12th power, minus one —
    the same quantity a 12-month revenue ratio expresses, so it stays
    comparable with the frozen clamp and with an annual reader's expectation.
    """
    if len(revenue) < 2 or revenue[0] <= 0 or revenue[-1] <= 0:
        return 0.0
    monthly = (revenue[-1] / revenue[0]) ** (1.0 / (len(revenue) - 1))
    return monthly**12 - 1.0


def is_usable_growth(revenue: Sequence[float]) -> bool:
    """False when the CAGR could not be computed and the flat 0.0 stands in."""
    return len(revenue) >= 2 and revenue[0] > 0.0 and revenue[-1] > 0.0


def derive_opex_split(opex: Sequence[float], revenue: Sequence[float]) -> tuple[float, float, bool]:
    """Least-squares split of opex into fixed ``F`` and variable ``v``.

    simulation.md §1: "OLS of opex on revenue over history; fallback
    F = 0.5*opex0, v = 0.5*opex0/rev0" with both constrained >= 0. The closed
    form below is exact for two parameters and needs no linear-algebra
    dependency. Three cases take the documented fallback instead of producing
    a meaningless slope: a singular design (flat revenue), a negative ``F``, or
    a negative ``v`` — all of which violate the frozen ``F, v >= 0`` constraint.
    """
    n = len(opex)
    if n == 0:
        return 0.0, 0.0, True
    sum_x = sum(revenue)
    sum_y = sum(opex)
    sum_xx = sum(x * x for x in revenue)
    sum_xy = sum(x * y for x, y in zip(revenue, opex, strict=True))
    denominator = n * sum_xx - sum_x * sum_x
    if abs(denominator) <= _OLS_SINGULAR_TOLERANCE:
        return _opex_fallback(opex, revenue)
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    if slope < 0.0 or intercept < 0.0:
        return _opex_fallback(opex, revenue)
    return intercept, slope, False


def _opex_fallback(opex: Sequence[float], revenue: Sequence[float]) -> tuple[float, float, bool]:
    """Frozen §1 fallback: F = 0.5*opex0, v = 0.5*opex0/rev0 (both >= 0)."""
    opex_0 = opex[0] if opex else 0.0
    revenue_0 = revenue[0] if revenue else 0.0
    fixed = 0.5 * opex_0
    variable = 0.5 * opex_0 / revenue_0 if revenue_0 > 0.0 else 0.0
    return fixed, variable, True


def clamp(value: float, low: float, high: float) -> float:
    """Clamp into the frozen §1 range for a parameter."""
    return max(low, min(high, value))


def derive_da(da: Sequence[float]) -> tuple[float, bool]:
    """Monthly D&A: trailing mean of the (already monthly) ``da`` field."""
    if not da:
        return 0.0, True
    return mean(da), False


def _ebt_of(period: PeriodFinancials) -> float | None:
    """Pre-tax earnings for one period, derived from the canonical schema.

    ``PeriodFinancials`` carries ``ebit`` and ``interest_expense`` but not
    ``ebt``, and §1 asks for the *effective* tax rate, so EBT is reconstructed
    as EBIT minus interest. Returns None when either leg is absent, so an
    unknowable rate falls back to the documented 25% instead of being invented.
    """
    if period.ebit is None or period.interest_expense is None:
        return None
    return float(period.ebit) - float(period.interest_expense)


def has_effective_tax(periods: Sequence[PeriodFinancials]) -> bool:
    """True when history exposes enough to compute a real effective tax rate."""
    return any(p.tax is not None and (_ebt_of(p) or 0.0) > 0.0 for p in periods)


def derive_tax_rate(periods: Sequence[PeriodFinancials]) -> float:
    """Effective tax rate = total tax / total EBT over the trailing window."""
    taxable = [(_ebt_of(p), float(p.tax or 0.0)) for p in periods if p.tax is not None]
    total_tax = sum(tax for ebt, tax in taxable if ebt is not None)
    total_ebt = sum(ebt for ebt, _ in taxable if ebt is not None)
    if total_ebt <= 0.0:
        return TAX_RATE_FALLBACK
    return total_tax / total_ebt


def derive_floating_share(latest: PeriodFinancials) -> tuple[float, bool]:
    """``phi`` from ``rate_exposure``; frozen fallback 0.5 when absent."""
    if latest.rate_exposure is None:
        return FALLBACK_FLOATING_SHARE, True
    return float(latest.rate_exposure.floating_debt_share), False


def derive_fx_shares(latest: PeriodFinancials) -> tuple[float, float, bool]:
    """``kappa_fx`` / ``rho_rev`` from ``fx_exposure``; frozen fallback 0.1."""
    if latest.fx_exposure is None:
        return FALLBACK_FX_SHARE, FALLBACK_FX_SHARE, True
    exposure = latest.fx_exposure
    return float(exposure.import_cost_share), float(exposure.foreign_revenue_share), False


def derive_commodity_share(latest: PeriodFinancials) -> tuple[float, bool]:
    """``kappa_c`` from ``commodity_exposure``; frozen fallback 0.2."""
    if latest.commodity_exposure is None:
        return FALLBACK_COMMODITY_SHARE, True
    return float(latest.commodity_exposure.cost_share), False


def derive_wc_days(
    periods: Sequence[PeriodFinancials], field: str, flow: Sequence[float]
) -> tuple[float, bool]:
    """Trailing mean of ``stock / flow * 30`` — the frozen DSO/DIO/DPO rule.

    The optional series may be partially absent: only months where both the
    stock and its flow exist contribute, so a genuinely missing
    working-capital field falls back to 0.0 days (no working capital) and says
    so in the assumption record, rather than being invented month by month.
    """
    ratios: list[float] = []
    for period, flow_value in zip(periods, flow, strict=True):
        stock = getattr(period, field)
        if stock is None or flow_value == 0.0:
            continue
        ratios.append(float(stock) / flow_value * DAYS_IN_MONTH)
    if not ratios:
        return 0.0, True
    return mean(ratios), False


def derive_capex(capex: Sequence[float]) -> tuple[float, bool]:
    """``Capex0`` as the trailing mean monthly capex; 0.0 when absent."""
    if not capex:
        return 0.0, True
    return mean(capex), False


def derive_initial_debt(latest: PeriodFinancials) -> tuple[float, bool]:
    """``D0`` from ``total_debt``; 0.0 (debt-free) when the field is absent."""
    if latest.total_debt is None:
        return 0.0, True
    return float(latest.total_debt), False


def build_amortization(latest: PeriodFinancials) -> list[DebtAmortization]:
    """Spread each ``debt_schedule`` bucket evenly across its month window.

    simulation.md §1: "from ``debt_schedule``; equal amortization inside
    buckets". An absent schedule yields no amortization, so debt simply does not
    amortise over the horizon and the disclosure in the assumptions record
    makes that visible.
    """
    schedule = latest.debt_schedule
    if not schedule:
        return []
    return [
        DebtAmortization(
            bucket=entry.bucket,
            months=DEBT_BUCKETS[entry.bucket],
            amount=float(entry.amount),
            monthly_principal=float(entry.amount) / DEBT_BUCKETS[entry.bucket],
        )
        for entry in schedule
    ]
