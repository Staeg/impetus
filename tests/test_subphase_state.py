from shared.protocol import SubPhase

from client.scenes.subphase_state import should_preserve_subphase


def test_restrain_choice_stays_open_while_cards_remain():
    assert should_preserve_subphase(
        SubPhase.RESTRAIN_CHOICE,
        {"change_cards": ["trade", "steal"]},
    ) is True


def test_shaping_choice_stays_open_while_cards_remain():
    assert should_preserve_subphase(
        SubPhase.SHAPING_CHOICE,
        {"change_cards": ["Guided Markets", "Shared Harvest"]},
    ) is True


def test_adaptation_choice_stays_open_while_cards_remain():
    assert should_preserve_subphase(
        SubPhase.ADAPTATION_CHOICE,
        {"change_cards": ["River Memory", "Stone Skin"]},
    ) is True


def test_choice_ui_closes_after_cards_are_cleared():
    assert should_preserve_subphase(
        SubPhase.RESTRAIN_CHOICE,
        {"change_cards": []},
    ) is False


def test_other_pending_subphases_keep_their_existing_guards():
    assert should_preserve_subphase(
        SubPhase.SPOILS_CHOICE,
        {"spoils_entries": ["pending"]},
    ) is True
    assert should_preserve_subphase(
        SubPhase.EXPAND_CHOICE,
        {"expand_choice_hexes": {(0, 0)}},
    ) is True
    assert should_preserve_subphase(
        SubPhase.WINNER_CHOICE,
        {"winner_choice_wars": [{"war_id": "w1"}]},
    ) is True
