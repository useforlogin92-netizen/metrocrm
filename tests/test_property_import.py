from app.services.property_import import UNASSIGNED_DEVELOPER, _resolve_developer_name


def test_explicit_developer_reference_wins():
    assert _resolve_developer_name("Any Project", "Known Developer", ["Other Developer"]) == "Known Developer"


def test_existing_developer_prefix_is_resolved():
    assert _resolve_developer_name("DGS Sheetal Sky", "", ["DGS Group", "Prestige Group"]) == "DGS Group"
    assert _resolve_developer_name("Prestige Garden Trails", "", ["DGS Group", "Prestige Group"]) == "Prestige Group"


def test_unknown_project_uses_safe_placeholder_not_numeric_guess():
    assert _resolve_developer_name("Unknown Project", "", ["DGS Group"]) == UNASSIGNED_DEVELOPER
