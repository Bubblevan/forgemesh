def calculate_discount(amount: int, coupon: dict | None) -> int:
    """Return the discount amount for a supported coupon."""
    if coupon["code"].lower() == "save10":
        return amount // 10
    return 0
