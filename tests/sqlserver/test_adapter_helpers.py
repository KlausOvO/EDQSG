import pytest

from edqsg.sqlserver.adapter import (
    quote_identifier,
    split_qualified_name,
    validate_sql_condition,
)


def test_identifier_quoting_and_splitting():
    assert quote_identifier("a]b") == "[a]]b]"
    assert split_qualified_name("Equipment") == ("dbo", "Equipment")
    assert split_qualified_name("x.Equipment") == ("x", "Equipment")


def test_condition_rejects_dangerous_sql():
    assert validate_sql_condition("quantity < 0") == "quantity < 0"
    with pytest.raises(ValueError):
        validate_sql_condition("1=1; DROP TABLE x")
