import pytest


@pytest.fixture(autouse=True)
def isolate_persistent_data(monkeypatch, tmp_path):
    from bot.utils import ai_store, data_manager, dm_store, ranks

    data_dir = tmp_path / "data"
    monkeypatch.setattr(data_manager, "BASE_DIR", data_dir)
    monkeypatch.setattr(data_manager, "USERS_FILE", data_dir / "users.json")
    monkeypatch.setattr(data_manager, "SETTINGS_FILE", data_dir / "settings.json")
    monkeypatch.setattr(data_manager, "MARKET_FILE", data_dir / "market.json")
    monkeypatch.setattr(data_manager, "LOANS_FILE", data_dir / "loans.json")
    monkeypatch.setattr(ranks, "STAFF_FILE", data_dir / "staff.json")
    monkeypatch.setattr(ranks, "LOGS_FILE", data_dir / "logs.json")
    monkeypatch.setattr(ai_store.ai_store, "db_path", data_dir / "vixen_ai.sqlite3")
    monkeypatch.setattr(ai_store.ai_store, "_initialized", False)
    monkeypatch.setattr(dm_store.dm_store, "db_path", data_dir / "dm.sqlite3")
    monkeypatch.setattr(dm_store.dm_store, "_initialized", False)