"""Domain errors for label profile resolution (Phase 1)."""


class SupplierLabelProfileNotConfiguredError(Exception):
    """Raised when SUPPLIER is forced but no applicable supplier config exists."""

    code = "SUPPLIER_LABEL_PROFILE_NOT_CONFIGURED"

    def __init__(
        self,
        message: str,
        *,
        label_kind: str | None = None,
        client_supplier_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.label_kind = label_kind
        self.client_supplier_id = client_supplier_id
