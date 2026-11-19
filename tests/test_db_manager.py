import pytest
import os
from src.database.db_manager import DatabaseManager
from src.database.models import Transaction

@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_transactions.db"
    return DatabaseManager(db_path=str(db_file))

def create_txn(**kwargs):
    defaults = {
        "source": "test_src",
        "imported_at": "2026-04-01T00:00:00Z"
    }
    defaults.update(kwargs)
    return Transaction(**defaults)

def test_db_initialization(tmp_path):
    db_file = tmp_path / "init_test.db"
    assert not os.path.exists(db_file)
    db = DatabaseManager(str(db_file))
    assert os.path.exists(db_file)
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r["name"] for r in cursor.fetchall()]
    conn.close()
    assert "transactions" in tables
    assert "import_log" in tables

def test_insert_and_get_transaction(db_manager):
    txn = create_txn(date="2026-04-01", amount=100.50, merchant="Test Merchant", source="amex")
    txn_id = db_manager.insert_transaction(txn)
    assert txn_id is not None
    retrieved = db_manager.get_transaction_by_id(txn_id)
    assert retrieved is not None
    assert retrieved.merchant == "Test Merchant"
    assert retrieved.amount == 100.50

def test_batch_insert(db_manager):
    txns = [
        create_txn(date="2026-04-01", amount=10.0, merchant="Merch A"),
        create_txn(date="2026-04-02", amount=20.0, merchant="Merch B")
    ]
    ids = db_manager.insert_transactions_batch(txns)
    assert len(ids) == 2

def test_batch_insert_empty(db_manager):
    ids = db_manager.insert_transactions_batch([])
    assert ids == []

def test_update_transaction(db_manager):
    txn = create_txn(date="2026-04-01", amount=50.0, merchant="To Update")
    txn_id = db_manager.insert_transaction(txn)
    success = db_manager.update_transaction(txn_id, {"merchant": "Updated Merch", "amount": 55.0})
    assert success is True
    retrieved = db_manager.get_transaction_by_id(txn_id)
    assert retrieved.merchant == "Updated Merch"
    assert retrieved.amount == 55.0

def test_update_transaction_empty(db_manager):
    txn = create_txn(date="2026-04-01", amount=50.0, merchant="Test")
    txn_id = db_manager.insert_transaction(txn)
    assert db_manager.update_transaction(txn_id, {}) is False

def test_get_transaction_by_splitwise_id(db_manager):
    txn = create_txn(date="2026-04-01", amount=50.0, merchant="Test", splitwise_id=12345)
    db_manager.insert_transaction(txn)
    found = db_manager.get_transaction_by_splitwise_id(12345)
    assert found is not None
    assert found.splitwise_id == 12345
    assert db_manager.get_transaction_by_splitwise_id(99999) is None

def test_get_transactions_by_date_range(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="Day 1"),
        create_txn(date="2026-04-15", amount=15.0, merchant="Day 15"),
        create_txn(date="2026-05-01", amount=20.0, merchant="Day 1 May")
    ])
    res = db_manager.get_transactions_by_date_range("2026-04-01", "2026-04-30")
    assert len(res) == 2

def test_get_transactions_by_date_range_include_deleted(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="Active"),
        create_txn(date="2026-04-02", amount=20.0, merchant="Deleted", splitwise_deleted_at="2026-04-05")
    ])
    active = db_manager.get_transactions_by_date_range("2026-04-01", "2026-04-30", include_deleted=False)
    assert len(active) == 1
    all_txns = db_manager.get_transactions_by_date_range("2026-04-01", "2026-04-30", include_deleted=True)
    assert len(all_txns) == 2


def test_get_unwritten_transactions(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="Unwritten"),
        create_txn(date="2026-04-02", amount=20.0, merchant="Written", written_to_sheet=1)
    ])
    unwritten = db_manager.get_unwritten_transactions()
    assert len(unwritten) == 1
    assert unwritten[0].merchant == "Unwritten"

def test_get_unwritten_transactions_by_year(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="Y2026"),
        create_txn(date="2025-04-01", amount=10.0, merchant="Y2025"),
    ])
    res = db_manager.get_unwritten_transactions(year=2026)
    assert len(res) == 1
    assert res[0].merchant == "Y2026"

def test_mark_written_to_sheet(db_manager):
    txn_id = db_manager.insert_transaction(create_txn(date="2026-04-01", amount=10.0, merchant="T"))
    db_manager.mark_written_to_sheet([txn_id], 2026)
    txn = db_manager.get_transaction_by_id(txn_id)
    assert txn.written_to_sheet == 1


def test_get_stats(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="A", source="amex"),
        create_txn(date="2026-04-02", amount=20.0, merchant="B", source="bofa", splitwise_id=999),
    ])
    stats = db_manager.get_stats()
    assert stats["total_transactions"] == 2
    assert stats["in_splitwise"] == 1

def test_update_splitwise_id(db_manager):
    txn_id = db_manager.insert_transaction(create_txn(date="2026-04-01", amount=10.0, merchant="T"))
    assert db_manager.update_splitwise_id(txn_id, 555) is True
    txn = db_manager.get_transaction_by_id(txn_id)
    assert txn.splitwise_id == 555

def test_update_transaction_from_splitwise(db_manager):
    txn_id = db_manager.insert_transaction(create_txn(date="2026-04-01", amount=10.0, merchant="T", splitwise_id=100))
    updated = db_manager.update_transaction_from_splitwise(100, {
        "cost": "25.0", "description": "Updated desc", "date": "2026-04-05",
        "category": {"name": "Food", "id": 5}, "subcategory": {"name": "Dining", "id": 50},
    })
    assert updated is True
    txn = db_manager.get_transaction_by_id(txn_id)
    assert txn.amount == 25.0
    assert db_manager.update_transaction_from_splitwise(99999, {"cost": "1.0"}) is False

def test_update_transaction_from_splitwise_deleted(db_manager):
    txn_id = db_manager.insert_transaction(create_txn(date="2026-04-01", amount=10.0, merchant="T", splitwise_id=200))
    updated = db_manager.update_transaction_from_splitwise(200, {"deleted_at": "2026-04-05T00:00:00Z"})
    assert updated is True
    txn = db_manager.get_transaction_by_id(txn_id)
    assert txn.splitwise_deleted_at == "2026-04-05T00:00:00Z"

def test_mark_deleted_by_splitwise_id(db_manager):
    txn_id = db_manager.insert_transaction(create_txn(date="2026-04-01", amount=10.0, merchant="T", splitwise_id=300))
    assert db_manager.mark_deleted_by_splitwise_id(300) is True
    txn = db_manager.get_transaction_by_id(txn_id)
    assert txn.splitwise_deleted_at is not None
    assert db_manager.mark_deleted_by_splitwise_id(99999) is False

def test_get_transactions_with_splitwise_ids(db_manager):
    db_manager.insert_transactions_batch([
        create_txn(date="2026-04-01", amount=10.0, merchant="A", splitwise_id=1),
        create_txn(date="2026-04-15", amount=20.0, merchant="B", splitwise_id=2),
        create_txn(date="2026-05-01", amount=30.0, merchant="C"),
    ])
    assert len(db_manager.get_transactions_with_splitwise_ids()) == 2
    assert len(db_manager.get_transactions_with_splitwise_ids(start_date="2026-04-10", end_date="2026-04-30")) == 1

def test_transaction_context_manager(db_manager):
    with db_manager.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        assert cursor.fetchone()[0] == 0

def test_append_deleted_filter():
    q = "SELECT * FROM t WHERE x = 1"
    assert "splitwise_deleted_at" in DatabaseManager._append_deleted_filter(q, include_deleted=False)
    assert "splitwise_deleted_at" not in DatabaseManager._append_deleted_filter(q, include_deleted=True)

def test_save_and_get_monthly_summary(db_manager):
    db_manager.save_monthly_summary(
        year_month="2026-01", total_spent_net=1000.0, avg_transaction=50.0,
        transaction_count=20, total_paid=1200.0, total_owed=200.0,
        cumulative_spending=1000.0, mom_change=0.0, written_to_sheet=False
    )
    result = db_manager.get_monthly_summary("2026-01")
    assert result is not None
    assert result["total_spent_net"] == 1000.0

def test_mark_monthly_summary_written(db_manager):
    db_manager.save_monthly_summary("2026-03", 500, 50, 10, 500, 0, 500, 0, written_to_sheet=False)
    db_manager.mark_monthly_summary_written("2026-03")
    result = db_manager.get_monthly_summary("2026-03")
    assert result["written_to_sheet"] == 1

def test_transaction_model_methods():
    txn = create_txn(date="2026-04-01", amount=10, merchant="T")
    txn.mark_written_to_sheet(2026, row_id=5)
    assert txn.written_to_sheet is True
    txn.update_splitwise_id(999)
    assert txn.splitwise_id == 999
    txn.mark_deleted_in_splitwise()
    assert txn.splitwise_deleted_at is not None

