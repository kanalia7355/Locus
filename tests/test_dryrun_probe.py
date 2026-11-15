from backend.dryrun_probe import add


def test_add_positive_integers() -> None:
    assert add(2, 3) == 5


def test_add_negative_integers() -> None:
    assert add(-4, -6) == -10
    assert add(-7, 3) == -4
