"""SQL receipt repository, optionally bound to an existing transaction."""

from __future__ import annotations

import pyodbc

from src.database.sqlserver import SqlServerClient
from src.domain.position_materialization.entities import (
    PositionMaterializationAssociationReceipt,
)


class SqlPositionMaterializationAssociationReceiptRepository:
    def __init__(
        self,
        client: SqlServerClient,
        *,
        connection: pyodbc.Connection | None = None,
    ) -> None:
        self._client = client
        self._connection = connection

    def save(self, receipt: PositionMaterializationAssociationReceipt) -> None:
        sql = """
        IF NOT EXISTS (
            SELECT 1 FROM dbo.position_materialization_association_receipts
            WHERE request_id = ?
        )
            INSERT INTO dbo.position_materialization_association_receipts
                (request_id, target_type, target_id, created_at, source_detection_id)
            VALUES (?, ?, ?, ?, ?)
        """
        params = (
            receipt.request_id,
            receipt.request_id,
            receipt.target_type,
            receipt.target_id,
            receipt.created_at,
            receipt.source_detection_id,
        )
        if self._connection is not None:
            self._connection.cursor().execute(sql, params)
            return
        with self._client.cursor() as cursor:
            cursor.execute(sql, params)

    def exists(self, request_id: str) -> bool:
        sql = """
        SELECT 1 FROM dbo.position_materialization_association_receipts
        WHERE request_id = ? AND target_type = 'IMAGE_RESULT'
        """
        if self._connection is not None:
            row = self._connection.cursor().execute(sql, (request_id,)).fetchone()
        else:
            with self._client.cursor() as cursor:
                cursor.execute(sql, (request_id,))
                row = cursor.fetchone()
        return row is not None
