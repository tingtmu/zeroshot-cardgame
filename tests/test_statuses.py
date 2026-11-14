import json

import pytest

from cardgame.models import StatusKind
from cardgame.statuses import (
    StatusDataError,
    StatusRules,
    load_default_status_rules,
    load_status_rules,
    parse_status_rules,
)


def _all_kinds(**overrides):
    """Valid rule data for every status kind, with per-kind overrides merged in."""
    entries = []
    for kind in StatusKind:
        entry = {"kind": kind.value}
        entry.update(overrides.get(kind.value, {}))
        entries.append(entry)
    return {"statuses": entries}


class TestDefaultData:
    def test_default_file_defines_poison_weak_and_shield(self):
        rules = load_default_status_rules()
        assert set(rules) == set(StatusKind)
        assert rules[StatusKind.POISON] == StatusRules(
            kind=StatusKind.POISON,
            turn_end_damage_per_stack=True,
            stacks_lost_per_turn=1,
        )
        assert rules[StatusKind.WEAK] == StatusRules(
            kind=StatusKind.WEAK,
            outgoing_damage_reduction_per_stack=25,
        )
        assert rules[StatusKind.SHIELD] == StatusRules(
            kind=StatusKind.SHIELD,
            absorbs_damage=True,
        )


class TestParseStatusRules:
    def test_missing_fields_default_to_no_behaviour(self):
        rules = parse_status_rules(_all_kinds())
        for kind in StatusKind:
            assert rules[kind] == StatusRules(kind=kind)

    def test_reads_every_field(self):
        data = _all_kinds(
            poison={"turn_end_damage_per_stack": True, "stacks_lost_per_turn": 2},
            weak={"outgoing_damage_reduction_per_stack": 10},
            shield={"absorbs_damage": True},
        )
        rules = parse_status_rules(data)
        assert rules[StatusKind.POISON].turn_end_damage_per_stack is True
        assert rules[StatusKind.POISON].stacks_lost_per_turn == 2
        assert rules[StatusKind.WEAK].outgoing_damage_reduction_per_stack == 10
        assert rules[StatusKind.SHIELD].absorbs_damage is True

    def test_keys_rules_by_kind(self):
        rules = parse_status_rules(_all_kinds())
        assert list(rules) == list(StatusKind)

    @pytest.mark.parametrize(
        "data, message",
        [
            ([], "top level"),
            ({}, "top level"),
            ({"statuses": {}}, "'statuses' must be a list"),
            ({"statuses": [], "extra": 1}, "top level: unknown keys"),
            ({"statuses": ["poison"]}, "must be an object"),
            ({"statuses": [{"absorbs_damage": True}]}, "missing 'kind'"),
            ({"statuses": [{"kind": "rage"}]}, "unknown status 'rage'"),
            (
                {"statuses": [{"kind": "poison", "bleed": 1}]},
                "unknown keys",
            ),
            (
                {"statuses": [{"kind": "poison", "absorbs_damage": "yes"}]},
                "absorbs_damage must be a bool",
            ),
            (
                {"statuses": [{"kind": "poison", "stacks_lost_per_turn": -1}]},
                "stacks_lost_per_turn must be >= 0",
            ),
            (
                {"statuses": [{"kind": "poison", "stacks_lost_per_turn": True}]},
                "stacks_lost_per_turn must be an int",
            ),
            (
                {"statuses": [{"kind": "weak", "outgoing_damage_reduction_per_stack": 101}]},
                "must be in 0..100",
            ),
            (
                {"statuses": [{"kind": "weak", "outgoing_damage_reduction_per_stack": 1.5}]},
                "must be an int",
            ),
            (
                {"statuses": [{"kind": "poison"}, {"kind": "poison"}]},
                "duplicate status 'poison'",
            ),
        ],
    )
    def test_rejects_malformed_entries(self, data, message):
        with pytest.raises(StatusDataError, match=message):
            parse_status_rules(data)

    def test_every_status_kind_must_have_rules(self):
        data = {"statuses": [{"kind": "poison"}, {"kind": "weak"}]}
        with pytest.raises(StatusDataError, match="no rules defined for statuses \\['shield'\\]"):
            parse_status_rules(data)


class TestLoadStatusRules:
    def test_loads_from_json_file(self, tmp_path):
        path = tmp_path / "statuses.json"
        path.write_text(json.dumps(_all_kinds(shield={"absorbs_damage": True})), encoding="utf-8")
        rules = load_status_rules(path)
        assert rules[StatusKind.SHIELD].absorbs_damage is True

    def test_invalid_json_raises(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{nope", encoding="utf-8")
        with pytest.raises(StatusDataError, match="invalid JSON"):
            load_status_rules(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_status_rules(tmp_path / "missing.json")


class TestStatusRulesValidation:
    def test_kind_must_be_a_status_kind(self):
        with pytest.raises(TypeError):
            StatusRules(kind="poison")  # type: ignore[arg-type]

    def test_reduction_bounds(self):
        assert StatusRules(kind=StatusKind.WEAK, outgoing_damage_reduction_per_stack=100)
        with pytest.raises(ValueError):
            StatusRules(kind=StatusKind.WEAK, outgoing_damage_reduction_per_stack=-1)
        with pytest.raises(ValueError):
            StatusRules(kind=StatusKind.WEAK, outgoing_damage_reduction_per_stack=101)

    def test_boolean_flags_must_be_bools(self):
        with pytest.raises(TypeError):
            StatusRules(kind=StatusKind.SHIELD, absorbs_damage=1)  # type: ignore[arg-type]
