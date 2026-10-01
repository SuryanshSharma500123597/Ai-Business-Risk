"""Registry-walking fixture-coverage enforcement (testing.md §5, requirements NFR2).

testing.md §5 (frozen): "100% of registry formulas covered by fixture tests (NFR2) —
enforced by a test that walks the registry and asserts a fixture exists per formula id."
requirements.md NFR2: "100% registry coverage by hand-computed fixtures; property tests pass".

Adding or renaming a metric in the registry without adding ``test_fixture_<metric_id>`` in
``test_risk_fixtures.py`` fails these tests.
"""

from backend.data_engine.contracts import SyntheticCompanyConfig
from backend.data_engine.ingest.synthetic import generate_company
from backend.risk_engine.contracts import REGISTRY_VERSION
from backend.risk_engine.engine import QuantitativeRiskEngine
from backend.risk_engine.registry import build_default_registry, interpolate_score
from backend.tests.unit import test_risk_fixtures

FIXTURE_PREFIX = "test_fixture_"


def test_every_registry_formula_has_a_hand_computed_fixture() -> None:
    metric_ids = sorted(
        definition.metric_id for definition in build_default_registry().list_metrics()
    )
    assert metric_ids, "the formula registry must not be empty"

    missing = [
        metric_id
        for metric_id in metric_ids
        if not callable(getattr(test_risk_fixtures, f"{FIXTURE_PREFIX}{metric_id}", None))
    ]
    assert not missing, f"registry formulas with no hand-computed fixture: {missing}"


def test_no_orphan_fixtures() -> None:
    metric_ids = {definition.metric_id for definition in build_default_registry().list_metrics()}
    fixture_ids = {
        name[len(FIXTURE_PREFIX) :]
        for name in dir(test_risk_fixtures)
        if name.startswith(FIXTURE_PREFIX)
    }
    orphans = sorted(fixture_ids - metric_ids)
    assert not orphans, f"fixtures not backed by a registry formula: {orphans}"


def test_registry_anchor_tables_are_well_formed() -> None:
    for definition in build_default_registry().list_metrics():
        assert definition.anchors, f"{definition.metric_id} defines no score anchors"
        values = [value for value, _ in definition.anchors]
        assert values == sorted(values), f"{definition.metric_id} anchors are not value-ordered"
        assert len(set(values)) == len(values), f"{definition.metric_id} has duplicate anchors"
        for _, score in definition.anchors:
            assert 0.0 <= score <= 100.0, f"{definition.metric_id} anchor score outside 0-100"


def test_interpolate_score_clamps_out_of_range_anchors() -> None:
    """D12: clamping applies at the endpoints too, not just between anchors."""
    assert interpolate_score(-5.0, [(0.0, 100.0), (1.0, 0.0)]) == 100.0
    assert interpolate_score(5.0, [(0.0, 100.0), (1.0, 0.0)]) == 0.0
    # Anchor scores outside the range are clamped rather than propagated.
    assert interpolate_score(-5.0, [(0.0, 150.0)]) == 100.0
    assert interpolate_score(5.0, [(0.0, -50.0)]) == 0.0


def test_every_formula_output_is_version_stamped() -> None:
    """requirements.md FR2: every formula returns value + score + registry_version."""
    dataset = generate_company(SyntheticCompanyConfig(seed=1001, periods=24))
    report = QuantitativeRiskEngine().evaluate_company(dataset)

    assert report.registry_version == REGISTRY_VERSION
    assert report.composite.registry_version == REGISTRY_VERSION
    assert report.metrics, "the engine must return metric results"

    for metric in report.metrics:
        assert metric.registry_version == REGISTRY_VERSION, f"{metric.metric_id} is unstamped"

    for dimension in report.composite.dimensions.values():
        assert dimension.registry_version == REGISTRY_VERSION
