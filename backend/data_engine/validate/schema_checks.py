"""Coverage matrix, range and period-sanity checks (frozen data.md §3).

Coverage is computed over the latest period by default (the snapshot an
analysis would score) with an all-periods mode for ingestion audits.
"""

from __future__ import annotations

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import (
    COVERAGE_GATE_PCT,
    MIN_PERIODS_FOR_ML,
    OPTIONAL_CONCEPTS,
    REQUIRED_CONCEPTS,
    CoverageIssue,
    GeneratedCompany,
    PeriodFinancials,
    ValidationReport,
)


def _present(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, list | dict):
        return len(value) > 0
    return True


def concept_present(period: PeriodFinancials, concept: str) -> bool:
    return _present(getattr(period, concept, None))


def coverage_report(periods: list[PeriodFinancials], mode: str = "latest") -> ValidationReport:
    """Compute the frozen coverage matrix.

    mode="latest": the most recent period (analysis snapshot).
    mode="all": a concept counts as present if it appears in any period.
    """
    if not periods:
        raise AppError(ErrorCode.VALIDATION_ERROR, "no periods to validate")

    def pick(concept: str) -> bool:
        if mode == "all":
            return any(concept_present(p, concept) for p in periods)
        return concept_present(periods[-1], concept)

    missing_required = [
        CoverageIssue(concept=concept, detail="absent")
        for concept in REQUIRED_CONCEPTS
        if not pick(concept)
    ]
    missing_optional = [
        CoverageIssue(concept=concept, detail="absent")
        for concept in OPTIONAL_CONCEPTS
        if not pick(concept)
    ]
    required_pct = 100.0 * (len(REQUIRED_CONCEPTS) - len(missing_required)) / len(REQUIRED_CONCEPTS)
    optional_pct = 100.0 * (len(OPTIONAL_CONCEPTS) - len(missing_optional)) / len(OPTIONAL_CONCEPTS)

    report = ValidationReport(
        required_pct=required_pct,
        optional_pct=optional_pct,
        missing_required=missing_required,
        missing_optional=missing_optional,
    )
    report = _attach_sanity_warnings(report, periods)
    if required_pct < COVERAGE_GATE_PCT:
        report = report.model_copy(update={"blocked": True})
    return report


def _attach_sanity_warnings(
    report: ValidationReport, periods: list[PeriodFinancials]
) -> ValidationReport:
    warnings = list(report.warnings)

    ends = [p.period_end for p in periods]
    if ends != sorted(ends):
        warnings.append("periods not sorted by period_end")
    if len(set(ends)) != len(ends):
        warnings.append("duplicate period_end values present")
    if len(periods) < MIN_PERIODS_FOR_ML:
        warnings.append(f"fewer than {MIN_PERIODS_FOR_ML} periods: ML features will be disabled")

    # margin range warnings (data.md §3 rule 3)
    for p in periods:
        for field in ("gross_profit", "opex", "ebitda", "net_income"):
            value = getattr(p, field)
            if value is not None and p.revenue:
                margin = value / p.revenue
                if not (-1.0 <= margin <= 1.0):
                    warnings.append(f"{field}/revenue margin {margin:.2f} outside [-1, 1]")
                    break

    return report.model_copy(update={"warnings": warnings})


def validate_company(company: GeneratedCompany) -> ValidationReport:
    """Coverage + sanity for a generated/ingested company (latest snapshot)."""
    return coverage_report(company.periods, mode="latest")


def enforce_coverage_gate(report: ValidationReport) -> None:
    """Raise the frozen DATA_COVERAGE_LOW error when the gate is not met."""
    if report.blocked:
        raise AppError(
            ErrorCode.DATA_COVERAGE_LOW,
            f"required-concept coverage {report.required_pct:.1f}% below "
            f"{COVERAGE_GATE_PCT:.0f}% gate",
            details={"missing": [i.concept for i in report.missing_required]},
        )


def latest_period(periods: list[PeriodFinancials]) -> PeriodFinancials:
    if not periods:
        raise AppError(ErrorCode.VALIDATION_ERROR, "no periods available")
    return max(periods, key=lambda p: p.period_end)
