"""Tests for RetailEnvironment lifecycle, isolation, and transactions."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent_reliability_lab.domains.retail.database import transaction
from agent_reliability_lab.domains.retail.environment import RetailEnvironment


def test_separate_environments_remain_isolated() -> None:
    with (
        RetailEnvironment("eligible_return") as env_a,
        RetailEnvironment("eligible_return") as env_b,
    ):
        path_a = env_a.db_path
        path_b = env_b.db_path
        assert path_a != path_b
        assert path_a.exists()
        assert path_b.exists()

        with transaction(env_a.connection):
            env_a.connection.execute(
                "UPDATE customers SET full_name = ? WHERE customer_id = ?",
                ("Changed Alice", "er_cust_alice"),
            )

        name_a = env_a.connection.execute(
            "SELECT full_name FROM customers WHERE customer_id = ?",
            ("er_cust_alice",),
        ).fetchone()[0]
        name_b = env_b.connection.execute(
            "SELECT full_name FROM customers WHERE customer_id = ?",
            ("er_cust_alice",),
        ).fetchone()[0]
        assert name_a == "Changed Alice"
        assert name_b == "Alice Example"


def test_successful_transactions_commit() -> None:
    with RetailEnvironment("eligible_return") as env:
        with transaction(env.connection):
            env.connection.execute(
                "UPDATE products SET name = ? WHERE product_id = ?",
                ("Updated Mug", "er_prod_mug"),
            )
        name = env.connection.execute(
            "SELECT name FROM products WHERE product_id = ?",
            ("er_prod_mug",),
        ).fetchone()[0]
        assert name == "Updated Mug"


def test_failed_transactions_roll_back() -> None:
    with RetailEnvironment("eligible_return") as env:
        original = env.connection.execute(
            "SELECT name FROM products WHERE product_id = ?",
            ("er_prod_mug",),
        ).fetchone()[0]
        with (
            pytest.raises(RuntimeError, match="force rollback"),
            transaction(env.connection),
        ):
            env.connection.execute(
                "UPDATE products SET name = ? WHERE product_id = ?",
                ("Should Not Persist", "er_prod_mug"),
            )
            raise RuntimeError("force rollback")
        name = env.connection.execute(
            "SELECT name FROM products WHERE product_id = ?",
            ("er_prod_mug",),
        ).fetchone()[0]
        assert name == original


def test_temporary_database_files_are_removed_after_cleanup() -> None:
    env = RetailEnvironment("eligible_return")
    env.open()
    path = env.db_path
    assert path.exists()
    env.close()
    assert not path.exists()


def test_cleanup_still_occurs_after_an_exception() -> None:
    path: Path | None = None
    with (
        pytest.raises(RuntimeError, match="boom"),
        RetailEnvironment("eligible_return") as env,
    ):
        path = env.db_path
        assert path.exists()
        raise RuntimeError("boom")
    assert path is not None
    assert not path.exists()


def test_connection_closes_reliably() -> None:
    env = RetailEnvironment("eligible_return")
    env.open()
    connection = env.connection
    env.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
