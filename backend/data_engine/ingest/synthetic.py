"""Deterministic synthetic company generator (frozen spec: data.md §4).

Same seed + same config => byte-identical output (R6). Accounting
identities hold exactly by construction: equity is the balance-sheet plug,
gross_profit = revenue − cogs, current_assets = cash + receivables +
inventory. Anomalies are injected as labelled step distortions and only
affect the flows they name (never the identities).
"""

from __future__ import annotations

import calendar
from datetime import date

import numpy as np

from backend.data_engine.contracts import (
    AnomalyInjection,
    AnomalyType,
    CommodityExposure,
    CompanyProfile,
    CompanySize,
    ConcentrationProfile,
    DebtScheduleEntry,
    Frequency,
    FxExposure,
    GeneratedCompany,
    HealthStatus,
    PeriodFinancials,
    RateExposure,
    Sector,
    ShareEntry,
    SyntheticCompanyConfig,
    hash_name,
)

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

# Sector templates: engineering ranges, not statistical fits (data.md §4
# calibration note). Values are monthly-figures scale factors.
_SECTOR_TEMPLATES: dict[Sector, dict[str, tuple[float, float]]] = {
    Sector.MANUFACTURING: {
        "gross_margin": (0.28, 0.38),
        "opex_ratio": (0.16, 0.22),
        "dso_days": (45.0, 60.0),
        "dio_days": (55.0, 75.0),
        "dpo_days": (40.0, 55.0),
        "capex_pct_revenue": (0.030, 0.050),
        "da_pct_assets": (0.0045, 0.0065),
    },
    Sector.RETAIL: {
        "gross_margin": (0.22, 0.30),
        "opex_ratio": (0.17, 0.23),
        "dso_days": (8.0, 15.0),
        "dio_days": (50.0, 70.0),
        "dpo_days": (35.0, 48.0),
        "capex_pct_revenue": (0.015, 0.030),
        "da_pct_assets": (0.0035, 0.0050),
    },
    Sector.SERVICES_SAAS: {
        "gross_margin": (0.68, 0.80),
        "opex_ratio": (0.45, 0.60),
        "dso_days": (30.0, 45.0),
        "dio_days": (1.0, 4.0),
        "dpo_days": (20.0, 32.0),
        "capex_pct_revenue": (0.006, 0.015),
        "da_pct_assets": (0.0040, 0.0060),
    },
}

_SIZE_SCALE: dict[CompanySize, float] = {
    CompanySize.SMALL: 8_000_000.0,
    CompanySize.MEDIUM: 80_000_000.0,
    CompanySize.LARGE: 800_000_000.0,
}

_HEALTH: dict[HealthStatus, dict[str, float]] = {
    HealthStatus.HEALTHY: {
        "cash_months": 4.5,
        "debt_ebitda": 1.2,
        "margin_shift": 0.03,
        "growth_boost": 0.003,
    },
    HealthStatus.STABLE: {
        "cash_months": 2.5,
        "debt_ebitda": 2.6,
        "margin_shift": 0.0,
        "growth_boost": 0.0,
    },
    HealthStatus.STRESSED: {
        "cash_months": 1.1,
        "debt_ebitda": 4.8,
        "margin_shift": -0.04,
        "growth_boost": -0.002,
    },
}

_CONCENTRATION_ENTRIES: dict[ConcentrationProfile, int] = {
    ConcentrationProfile.DISPERSED: 14,
    ConcentrationProfile.MODERATE: 8,
    ConcentrationProfile.CONCENTRATED: 4,
}
_CONCENTRATION_ALPHA: dict[ConcentrationProfile, float] = {
    # smaller alpha => heavier tail => higher HHI (Dirichlet concentration);
    # tuned so realized HHI stays within the frozen 0.05–0.6 band (data.md §4)
    ConcentrationProfile.DISPERSED: 6.0,
    ConcentrationProfile.MODERATE: 1.4,
    ConcentrationProfile.CONCENTRATED: 0.40,
}

_COMMODITY_BY_SECTOR: dict[Sector, str] = {
    Sector.MANUFACTURING: "steel",
    Sector.RETAIL: "freight_fuel",
    Sector.SERVICES_SAAS: "cloud_compute",
}

_COMPANY_NAME_PREFIX = (
    "Vertex",
    "Northline",
    "Kestrel",
    "Amberly",
    "Solent",
    "Bramwick",
    "Corvane",
    "Ellingsen",
    "Fairmount",
    "Greystone",
)
_COMPANY_NAME_SUFFIX = {
    Sector.MANUFACTURING: "Industries",
    Sector.RETAIL: "Retail Group",
    Sector.SERVICES_SAAS: "Software",
}


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _month_start(year: int, month: int) -> date:
    return date(year, month, 1)


def _sum_present_flow(periods: list[PeriodFinancials], field: str) -> float | None:
    values = [getattr(period, field) for period in periods]
    if any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _draw_shares(rng: np.random.Generator, n: int, alpha: float) -> list[float]:
    """Dirichlet-drawn shares, rounded to 4 dp and re-normalized to sum≈1."""
    raw = rng.dirichlet(np.full(n, alpha))
    rounded = np.round(raw, 4)
    rounded[-1] = round(1.0 - rounded[:-1].sum(), 4)
    return [float(x) for x in rounded]


def _concentrated_shares(rng: np.random.Generator, n: int) -> list[float]:
    """Explicit top-share construction: leader uniform in [0.45, 0.58], the
    remainder split among the others. Bounds realized HHI inside the frozen
    0.05–0.6 band deterministically (Dirichlet variance was too high)."""
    top = float(rng.uniform(0.45, 0.58))
    rest = [round(s * (1.0 - top), 4) for s in _draw_shares(rng, n - 1, 1.0)]
    shares = [top, *rest]
    shares[-1] = round(1.0 - sum(shares[:-1]), 4)
    return shares


def _bucket_entries(
    rng: np.random.Generator,
    profile: ConcentrationProfile,
    hashed: bool,
    name_pool: tuple[str, ...],
) -> list[ShareEntry]:
    n = _CONCENTRATION_ENTRIES[profile]
    if profile is ConcentrationProfile.CONCENTRATED:
        shares = _concentrated_shares(rng, n)
    else:
        shares = _draw_shares(rng, n, _CONCENTRATION_ALPHA[profile])
    entries: list[ShareEntry] = []
    for i, share in enumerate(shares):
        label = name_pool[int(rng.integers(0, len(name_pool)))] + f"-{i:02d}"
        entries.append(
            ShareEntry(name_hash=hash_name(label), share=share)
            if hashed
            else ShareEntry(name=label, share=share)
        )
    return entries


def _anomaly_active(injection: AnomalyInjection, month_index: int) -> bool:
    return injection.start_month <= month_index < injection.start_month + injection.duration_months


def generate_company(config: SyntheticCompanyConfig) -> GeneratedCompany:
    """Generate one canonical company deterministically from the config seed."""
    rng = np.random.default_rng(config.seed)
    tpl = _SECTOR_TEMPLATES[config.sector]
    health = _HEALTH[config.health]

    # Frozen data.md §4: annual configs count years; generate months then aggregate.
    month_count = config.periods * 12 if config.frequency is Frequency.ANNUAL else config.periods

    def draw(key: str) -> float:
        lo, hi = tpl[key]
        return float(rng.uniform(lo, hi))

    name = (
        _COMPANY_NAME_PREFIX[int(rng.integers(0, len(_COMPANY_NAME_PREFIX)))]
        + " "
        + _COMPANY_NAME_SUFFIX[config.sector]
    )

    base_revenue = _SIZE_SCALE[config.size] * float(rng.uniform(0.85, 1.15)) / 12.0
    gross_margin = min(0.85, max(0.05, draw("gross_margin") + health["margin_shift"]))
    opex_ratio = draw("opex_ratio")
    dso = draw("dso_days")
    dio = draw("dio_days")
    dpo = draw("dpo_days")
    capex_pct = draw("capex_pct_revenue")
    da_pct_assets = draw("da_pct_assets")

    # seasonality: retail-weighted cosine, deterministic phase
    seasonal_amp = 0.12 if config.effective_seasonality else 0.0
    noise = float(rng.uniform(0.008, 0.02))

    start_year, start_month = 2023, 1

    periods: list[PeriodFinancials] = []
    for t in range(1, month_count + 1):
        month_index = t
        year = start_year + (start_month + t - 2) // 12
        month = (start_month + t - 2) % 12 + 1

        drift = 1.0 + (config.growth_drift_monthly_pct / 100.0 + health["growth_boost"]) * (t - 1)
        season = 1.0 + seasonal_amp * np.cos(2 * np.pi * (month - 1) / 12.0)
        wiggle = float(rng.normal(1.0, noise))
        revenue = base_revenue * drift * season * max(wiggle, 0.5)

        month_gm = gross_margin
        receivable_days = dso
        month_opex_ratio = opex_ratio

        for injection in config.inject_anomalies:
            if not _anomaly_active(injection, month_index):
                continue
            if injection.type is AnomalyType.MARGIN_COLLAPSE:
                month_gm = max(0.02, month_gm - injection.magnitude * month_gm)
            elif injection.type is AnomalyType.RECEIVABLE_SPIKE:
                receivable_days = receivable_days * (1.0 + injection.magnitude)
            elif injection.type is AnomalyType.COST_EXPLOSION:
                month_opex_ratio = month_opex_ratio * (1.0 + injection.magnitude)

        cogs = revenue * (1.0 - month_gm)
        gross_profit = revenue - cogs
        opex = revenue * month_opex_ratio
        ebitda = gross_profit - opex

        receivables = revenue * receivable_days / 30.0
        inventory = cogs * dio / 30.0
        payables = cogs * dpo / 30.0

        # debt sized from annualized EBITDA (clamped positive for stressed health)
        annualized_ebitda = max(ebitda * 12.0, base_revenue * 12.0 * 0.05)
        total_debt = health["debt_ebitda"] * annualized_ebitda
        st_debt = total_debt * float(rng.uniform(0.2, 0.4))
        lt_debt = total_debt - st_debt
        interest_rate = float(rng.uniform(0.07, 0.11))
        interest_expense = total_debt * interest_rate / 12.0

        cash = max(
            revenue * health["cash_months"] * float(rng.uniform(0.9, 1.1)),
            0.0,
        )
        current_assets = cash + receivables + inventory
        # current liabilities: payables + short-term debt + accrual buffer
        current_liabilities = payables + st_debt + revenue * 0.04
        total_assets = current_assets + total_debt * float(rng.uniform(0.6, 0.9)) + revenue * 2.0
        total_liabilities = current_liabilities + lt_debt
        # balance-sheet plug: identities hold exactly
        equity = total_assets - total_liabilities

        da = total_assets * da_pct_assets
        ebit = ebitda - da
        ebt = ebit - interest_expense
        tax = max(0.0, ebt) * 0.25
        net_income = ebt - tax

        capex = revenue * capex_pct
        ocf = net_income + da - (receivables - revenue * dso / 30.0)

        # concentration buckets drawn once per company would repeat every period;
        # draw per period from the same stream for stable-but-varying shares
        customers = _bucket_entries(
            rng, config.concentration, True, tuple(f"cust-{_MONTHS[m % 12]}" for m in range(12))
        )
        suppliers = _bucket_entries(
            rng, config.concentration, True, tuple(f"supp-{_MONTHS[m % 12]}" for m in range(12))
        )
        products = _bucket_entries(
            rng, config.concentration, False, tuple(f"line-{_MONTHS[m % 12]}" for m in range(12))
        )
        regions = _bucket_entries(
            rng, config.concentration, False, ("north", "south", "east", "west", "central")
        )

        fx_share = (
            float(rng.uniform(0.05, 0.25))
            if config.sector is not Sector.SERVICES_SAAS
            else float(rng.uniform(0.20, 0.45))
        )
        periods.append(
            PeriodFinancials(
                period_start=_month_start(year, month),
                period_end=_month_end(year, month),
                fiscal_year=year,
                quarter=(month - 1) // 3 + 1,
                frequency=Frequency.MONTHLY,
                source="synthetic",
                revenue=revenue,
                cogs=cogs,
                gross_profit=gross_profit,
                opex=opex,
                ebitda=ebitda,
                da=da,
                ebit=ebit,
                interest_expense=interest_expense,
                tax=tax,
                net_income=net_income,
                cash=cash,
                receivables=receivables,
                inventory=inventory,
                payables=payables,
                current_assets=current_assets,
                current_liabilities=current_liabilities,
                total_assets=total_assets,
                total_liabilities=total_liabilities,
                equity=equity,
                total_debt=total_debt,
                st_debt=st_debt,
                lt_debt=lt_debt,
                capex=capex,
                ocf=ocf,
                fcf=ocf - capex,
                dividends=None,
                customers=customers,
                suppliers=suppliers,
                products=products,
                regions=regions,
                fx_exposure=FxExposure(
                    foreign_revenue_share=fx_share * float(rng.uniform(0.6, 1.0)),
                    import_cost_share=fx_share * float(rng.uniform(0.6, 1.0)),
                ),
                commodity_exposure=CommodityExposure(
                    input=_COMMODITY_BY_SECTOR[config.sector],
                    cost_share=float(rng.uniform(0.10, 0.35)),
                ),
                rate_exposure=RateExposure(
                    floating_debt_share=float(rng.uniform(0.3, 0.7)),
                ),
                debt_schedule=[
                    DebtScheduleEntry(bucket="0-3m", amount=st_debt * 0.5),
                    DebtScheduleEntry(bucket="3-12m", amount=st_debt * 0.5),
                    DebtScheduleEntry(bucket="1-3y", amount=lt_debt * 0.4),
                    DebtScheduleEntry(bucket="3y+", amount=lt_debt * 0.6),
                ],
            )
        )

    if config.frequency is Frequency.ANNUAL:
        periods = _aggregate_annual(periods)

    profile = CompanyProfile(
        name=name,
        sector=config.sector,
        currency=config.currency,
        description=(
            f"Synthetic {config.health.value} {config.sector.value} company "
            f"({config.size.value}, seed {config.seed})"
        ),
    )
    return GeneratedCompany(profile=profile, periods=periods, generator_config=config)


def _aggregate_annual(monthly: list[PeriodFinancials]) -> list[PeriodFinancials]:
    """Aggregate 12k monthly periods into k annual periods (flows summed,
    stocks/buckets/exposures taken at period end; identities preserved)."""
    annual: list[PeriodFinancials] = []
    for year_start in range(0, len(monthly), 12):
        chunk = monthly[year_start : year_start + 12]
        last = chunk[-1]
        flow_fields = (
            "revenue",
            "cogs",
            "gross_profit",
            "opex",
            "ebitda",
            "da",
            "ebit",
            "interest_expense",
            "tax",
            "net_income",
            "capex",
            "ocf",
            "fcf",
        )

        aggregated = {f: _sum_present_flow(chunk, f) for f in flow_fields}
        # annual gross_profit identity: recompute when both operands exist
        if aggregated["revenue"] is not None and aggregated["cogs"] is not None:
            aggregated["gross_profit"] = aggregated["revenue"] - aggregated["cogs"]
        stock_fields = (
            "cash",
            "receivables",
            "inventory",
            "payables",
            "current_assets",
            "current_liabilities",
            "total_assets",
            "total_liabilities",
            "equity",
            "total_debt",
            "st_debt",
            "lt_debt",
        )
        stocks = {f: getattr(last, f) for f in stock_fields}
        annual.append(
            last.model_copy(
                update={
                    "period_start": chunk[0].period_start,
                    "fiscal_year": last.period_end.year,
                    "quarter": None,
                    "frequency": Frequency.ANNUAL,
                    **aggregated,
                    **stocks,
                }
            )
        )
    return annual


def canonical_fixture_configs() -> dict[str, SyntheticCompanyConfig]:
    """Frozen fixture set (testing.md §2): seeds 1001–1005."""
    return {
        "mfg_healthy": SyntheticCompanyConfig(
            sector=Sector.MANUFACTURING, health=HealthStatus.HEALTHY, seed=1001
        ),
        "mfg_stressed": SyntheticCompanyConfig(
            sector=Sector.MANUFACTURING, health=HealthStatus.STRESSED, seed=1002
        ),
        "retail_seasonal": SyntheticCompanyConfig(
            sector=Sector.RETAIL, seasonality=True, seed=1003
        ),
        "saas_stable": SyntheticCompanyConfig(sector=Sector.SERVICES_SAAS, seed=1004),
        "mfg_concentrated_anomalies": SyntheticCompanyConfig(
            sector=Sector.MANUFACTURING,
            concentration=ConcentrationProfile.CONCENTRATED,
            inject_anomalies=[
                AnomalyInjection(
                    type=AnomalyType.MARGIN_COLLAPSE,
                    start_month=14,
                    duration_months=4,
                    magnitude=0.5,
                ),
                AnomalyInjection(
                    type=AnomalyType.RECEIVABLE_SPIKE,
                    start_month=20,
                    duration_months=3,
                    magnitude=0.8,
                ),
            ],
            seed=1005,
        ),
    }


def generate_canonical_fixtures() -> dict[str, GeneratedCompany]:
    return {key: generate_company(cfg) for key, cfg in canonical_fixture_configs().items()}
