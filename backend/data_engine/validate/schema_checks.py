"""Coverage matrix, range and period-sanity checks (frozen data.md §3).

Coverage is computed over the latest period by default (the snapshot an
analysis would score) with an all-periods mode for ingestion audits.
"""

from __future__ import annotations

from typing import Literal

from backend.core.errors import AppError, ErrorCode
from backend.data_engine.contracts import (
    COVERAGE_GATE_PCT,
    MIN_PERIODS_FOR_ML,
    OPTIONAL_CONCEPTS,
    REQUIRED_CONCEPTS,
    CompanyDataset,
    CoverageIssue,
    GeneratedCompany,
    PeriodFinancials,
    QualityIssue,
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
    issues = list(report.issues)

    def add_warning(code: str, detail: str, *, period_index: int | None = None) -> None:
        warnings.append(detail)
        issues.append(
            QualityIssue(severity="warning", code=code, detail=detail, period_index=period_index)
        )

    ends = [p.period_end for p in periods]
    if ends != sorted(ends):
        add_warning("PERIOD_ORDER", "periods not sorted by period_end")
    if len(set(ends)) != len(ends):
        add_warning("DUPLICATE_PERIOD", "duplicate period_end values present")
    if len(periods) < MIN_PERIODS_FOR_ML:
        add_warning(
            "ML_PERIODS_SHORT",
            f"fewer than {MIN_PERIODS_FOR_ML} periods: ML features will be disabled",
        )

    # margin range warnings (data.md §3 rule 3)
    for index, p in enumerate(periods):
        for field in ("gross_profit", "opex", "ebitda", "net_income"):
            value = getattr(p, field)
            if value is not None and p.revenue:
                margin = value / p.revenue
                if not (-1.0 <= margin <= 1.0):
                    add_warning(
                        "MARGIN_OUT_OF_RANGE",
                        f"{field}/revenue margin {margin:.2f} outside [-1, 1]",
                        period_index=index,
                    )
                    break

    return report.model_copy(update={"warnings": warnings, "issues": issues})


def validate_company(company: GeneratedCompany) -> ValidationReport:
    """Legacy latest-snapshot coverage helper; use validate_dataset for storage."""
    return coverage_report(company.periods, mode="latest")


def validate_dataset(company: CompanyDataset) -> ValidationReport:
    """Validate coverage plus every period before a dataset is persisted.

    Coverage remains a latest-period analysis snapshot for compatibility. All
    periods are checked for ordering, duplicate dates, source metadata and
    accounting identities. Only typed ``error`` findings block storage;
    warnings and informational findings are retained for disclosure.
    """
    from backend.data_engine.validate.identities import check_all_periods

    report = coverage_report(company.periods, mode="latest")
    issues = list(report.issues)
    warnings = list(report.warnings)

    def add_issue(
        severity: Literal["error", "warning", "info"],
        code: str,
        detail: str,
        *,
        period_index: int | None = None,
    ) -> None:
        nonlocal report
        issues.append(
            QualityIssue(severity=severity, code=code, detail=detail, period_index=period_index)
        )
        if severity == "warning":
            warnings.append(detail)

    if report.required_pct < COVERAGE_GATE_PCT:
        add_issue(
            "error",
            "DATA_COVERAGE_LOW",
            f"required-concept coverage {report.required_pct:.1f}% below "
            f"{COVERAGE_GATE_PCT:.0f}% gate",
        )

    ends = [p.period_end for p in company.periods]
    if ends != sorted(ends):
        add_issue("error", "PERIOD_ORDER", "periods not sorted by period_end")
    if len(set(ends)) != len(ends):
        add_issue("error", "DUPLICATE_PERIOD", "duplicate period_end values present")

    sources = {p.source.strip() for p in company.periods}
    if any(not source for source in sources):
        add_issue("error", "SOURCE_MISSING", "every period must carry a non-empty source")
    if len(sources) > 1:
        add_issue("warning", "MIXED_SOURCES", "dataset contains periods from mixed sources")

    for index, period in enumerate(company.periods):
        if period.period_start > period.period_end:
            add_issue(
                "error",
                "PERIOD_DATE_RANGE",
                "period_start is after period_end",
                period_index=index,
            )

    for index, violations in check_all_periods(company.periods).items():
        for violation in violations:
            add_issue("error", "ACCOUNTING_IDENTITY", violation, period_index=index)

    # A short series is a disclosed limitation, not a storage failure.
    if len(company.periods) < MIN_PERIODS_FOR_ML:
        add_issue(
            "info",
            "ML_PERIODS_SHORT",
            f"fewer than {MIN_PERIODS_FOR_ML} periods: ML features will be disabled",
        )

    return report.model_copy(
        update={
            "issues": issues,
            "warnings": warnings,
            "blocked": any(issue.severity == "error" for issue in issues),
        }
    )


def enforce_coverage_gate(report: ValidationReport) -> None:
    """Raise coverage or validation failure after strict dataset validation."""
    if report.required_pct < COVERAGE_GATE_PCT:
        raise AppError(
            ErrorCode.DATA_COVERAGE_LOW,
            f"required-concept coverage {report.required_pct:.1f}% below "
            f"{COVERAGE_GATE_PCT:.0f}% gate",
            details={"missing": [i.concept for i in report.missing_required]},
        )
    if report.blocked:
        raise AppError(
            ErrorCode.VALIDATION_ERROR,
            "dataset contains blocking data-quality errors",
            details={"errors": [issue.model_dump() for issue in report.errors]},
        )


def latest_period(periods: list[PeriodFinancials]) -> PeriodFinancials:
    if not periods:
        raise AppError(ErrorCode.VALIDATION_ERROR, "no periods available")
    return max(periods, key=lambda p: p.period_end)
