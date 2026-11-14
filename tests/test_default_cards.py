from cardgame.loader import load_default_cards
from cardgame.models import Effect, EffectKind, StatusKind


def test_default_data_file_has_three_example_cards():
    cards = load_default_cards()
    assert list(cards) == ["Strike", "Guard", "Venom Dart"]


def test_strike_deals_damage():
    card = load_default_cards()["Strike"]
    assert card.cost == 1
    assert card.effects == (Effect(kind=EffectKind.DAMAGE, amount=6),)


def test_guard_grants_shield():
    card = load_default_cards()["Guard"]
    assert card.cost == 1
    assert card.effects == (Effect(kind=EffectKind.SHIELD, amount=5),)


def test_venom_dart_damages_and_poisons():
    card = load_default_cards()["Venom Dart"]
    assert card.cost == 1
    assert card.effects == (
        Effect(kind=EffectKind.DAMAGE, amount=3),
        Effect(kind=EffectKind.APPLY_STATUS, status=StatusKind.POISON, stacks=2, duration=3),
    )
