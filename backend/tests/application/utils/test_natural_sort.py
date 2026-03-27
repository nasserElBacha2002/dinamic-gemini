from src.application.utils.natural_sort import natural_sort_key_parts


def test_natural_sort_orders_numeric_chunks() -> None:
    keys = ["A2", "A10", "A1"]
    sorted_codes = sorted(keys, key=natural_sort_key_parts)
    assert sorted_codes == ["A1", "A2", "A10"]


def test_natural_sort_empty_and_stable() -> None:
    assert natural_sort_key_parts("") == ("",)
    assert natural_sort_key_parts("X") == ("x",)
