from backend.dryrun_probe2 import subtract


def test_subtract_positive_integers() -> None:
    assert subtract(10, 3) == 7
    assert subtract(5, 8) == -3


def test_subtract_negative_integers() -> None:
    assert subtract(-5, -2) == -3
    assert subtract(-4, 6) == -10
    assert subtract(5, -3) == 8
