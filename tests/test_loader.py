import json

import pytest

from cardgame.loader import CardDataError, load_cards, parse_cards
from cardgame.models import Card, Effect, EffectKind, StatusKind


def _write(tmp_path, data):
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _card(**overrides):
    base = {"name": "Test", "cost": 1, "effects": [{"type": "damage", "amount": 2}]}
    base.update(overrides)
    return base


class TestParseCards:
    def test_parses_all_effect_kinds(self):
        data = {
            "cards": [
                {
                    "name": "Everything",
                    "cost": 2,
                    "effects": [
                        {"type": "damage", "amount": 4},
                        {"type": "shield", "amount": 3},
                        {"type": "draw", "amount": 1},
                        {"type": "apply_status", "status": "weak", "stacks": 1, "duration": 2},
                    ],
                }
            ]
        }
        cards = parse_cards(data)
        card = cards["Everything"]
        assert isinstance(card, Card)
        assert card.cost == 2
        assert card.effects == (
            Effect(kind=EffectKind.DAMAGE, amount=4),
            Effect(kind=EffectKind.SHIELD, amount=3),
            Effect(kind=EffectKind.DRAW, amount=1),
            Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.WEAK, stacks=1, duration=2),
        )

    def test_keys_cards_by_name_in_definition_order(self):
        data = {"cards": [_card(name="B"), _card(name="A")]}
        assert list(parse_cards(data)) == ["B", "A"]

    def test_card_with_no_effects_is_allowed(self):
        cards = parse_cards({"cards": [_card(effects=[])]})
        assert cards["Test"].effects == ()

    def test_empty_card_list_is_allowed(self):
        assert parse_cards({"cards": []}) == {}

    @pytest.mark.parametrize(
        "data, message",
        [
            ([], "top level"),
            ({}, "top level"),
            ({"cards": {}}, "'cards' must be a list"),
            ({"cards": [], "extra": 1}, "unknown keys"),
            ({"cards": ["nope"]}, "must be an object"),
            ({"cards": [_card(extra=1)]}, "unknown keys"),
            ({"cards": [_card(name="")]}, "'name' must be a non-empty string"),
            ({"cards": [_card(name=5)]}, "'name' must be a non-empty string"),
            ({"cards": [_card(cost="1")]}, "'cost' must be an integer"),
            ({"cards": [_card(cost=True)]}, "'cost' must be an integer"),
            ({"cards": [_card(cost=-1)]}, "must be >= 0"),
            ({"cards": [_card(effects="damage")]}, "'effects' must be a list"),
            ({"cards": [_card(effects=["damage"])]}, "effect must be an object"),
            ({"cards": [_card(effects=[{"amount": 1}])]}, "missing 'type'"),
            ({"cards": [_card(effects=[{"type": "explode", "amount": 1}])]}, "unknown effect type"),
            ({"cards": [_card(effects=[{"type": "damage"}])]}, "missing 'amount'"),
            ({"cards": [_card(effects=[{"type": "damage", "amount": 0}])]}, "must be >= 1"),
            ({"cards": [_card(effects=[{"type": "damage", "amount": 1, "x": 2}])]}, "unknown keys"),
            (
                {"cards": [_card(effects=[{"type": "apply_status", "stacks": 1, "duration": 1}])]},
                "missing 'status'",
            ),
            (
                {"cards": [_card(effects=[{"type": "apply_status", "status": "rage", "stacks": 1, "duration": 1}])]},
                "unknown status",
            ),
            (
                {"cards": [_card(effects=[{"type": "apply_status", "status": "poison", "stacks": 1}])]},
                "missing 'duration'",
            ),
            (
                {"cards": [_card(effects=[{"type": "apply_status", "status": "poison", "stacks": 0, "duration": 1}])]},
                "must be >= 1",
            ),
            (
                {"cards": [_card(effects=[{"type": "apply_status", "status": "poison", "stacks": 1, "duration": 1, "amount": 2}])]},
                "unknown keys",
            ),
            ({"cards": [_card(name="Dup"), _card(name="Dup")]}, "duplicate card name 'Dup'"),
        ],
    )
    def test_rejects_malformed_data(self, data, message):
        with pytest.raises(CardDataError, match=message):
            parse_cards(data)


class TestLoadCards:
    def test_loads_from_json_file(self, tmp_path):
        path = _write(tmp_path, {"cards": [_card(name="Jab")]})
        cards = load_cards(path)
        assert cards["Jab"].effects == (Effect(kind=EffectKind.DAMAGE, amount=2),)

    def test_accepts_string_path(self, tmp_path):
        path = _write(tmp_path, {"cards": [_card()]})
        assert "Test" in load_cards(str(path))

    def test_invalid_json_raises_card_data_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(CardDataError, match="invalid JSON"):
            load_cards(path)

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_cards(tmp_path / "missing.json")
