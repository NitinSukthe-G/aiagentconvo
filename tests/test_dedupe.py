from app.services.dedupe import mark_seen_if_new


def test_first_sighting_is_new(fake_redis):
    assert mark_seen_if_new("wamid.abc") is True


def test_second_sighting_is_duplicate(fake_redis):
    assert mark_seen_if_new("wamid.abc") is True
    assert mark_seen_if_new("wamid.abc") is False


def test_different_ids_are_independent(fake_redis):
    assert mark_seen_if_new("wamid.one") is True
    assert mark_seen_if_new("wamid.two") is True
