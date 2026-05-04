from src.database.migrations import service as migration_service


def test_split_sql_batches_supports_go_separator():
    sql = """
    SELECT 1;
    GO
    SELECT 2;
    """.strip()
    parts = migration_service._split_sql_batches(sql)
    assert parts == ["SELECT 1;", "SELECT 2;"]


def test_ensure_schema_compatibility_marks_incompatible_when_behind(monkeypatch):
    class DummyClient:
        pass

    monkeypatch.setattr(migration_service, "_ensure_migration_table", lambda _client: None)
    monkeypatch.setattr(
        migration_service, "_fetch_last_applied_version", lambda _client, _svc: "0002"
    )

    status = migration_service.ensure_schema_compatibility(
        client=DummyClient(),
        service="inventory-api",
        required_version="0003",
    )
    assert status.compatible is False
    assert status.current_version == "0002"
    assert "behind required version 0003" in (status.reason or "")


def test_get_migration_status_lists_pending(monkeypatch):
    class DummyClient:
        pass

    monkeypatch.setattr(migration_service, "_ensure_migration_table", lambda _client: None)
    monkeypatch.setattr(
        migration_service,
        "_list_migration_files",
        lambda: [
            migration_service.MigrationFile(
                "0001", "baseline", migration_service.Path("a.sql"), "x"
            ),
            migration_service.MigrationFile(
                "0002", "add_jobs", migration_service.Path("b.sql"), "y"
            ),
        ],
    )
    monkeypatch.setattr(
        migration_service, "_fetch_applied_versions", lambda _client, _svc: ["0001"]
    )
    monkeypatch.setattr(
        migration_service, "_fetch_last_applied_version", lambda _client, _svc: "0001"
    )

    status = migration_service.get_migration_status(client=DummyClient(), service="inventory-api")
    assert status.pending_versions == ["0002"]
    assert status.compatible is False
