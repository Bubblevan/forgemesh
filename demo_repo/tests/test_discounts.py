from discounts import calculate_discount


def test_missing_coupon_is_not_an_error() -> None:
    assert calculate_discount(100, None) == 0


def test_save10_coupon_applies_ten_percent_discount() -> None:
    assert calculate_discount(250, {"code": "SAVE10"}) == 25
