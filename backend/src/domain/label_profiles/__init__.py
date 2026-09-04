"""Label recognition profile domain — Phase 1 (ITEM/POSITION source selection)."""

from src.domain.label_profiles.entities import (
    ClientSupplierLabelProfile,
    ResolvedLabelProfile,
    ResolvedLabelProfiles,
)
from src.domain.label_profiles.errors import SupplierLabelProfileNotConfiguredError
from src.domain.label_profiles.kinds import LabelKind, LabelProfileSource

__all__ = [
    "ClientSupplierLabelProfile",
    "LabelKind",
    "LabelProfileSource",
    "ResolvedLabelProfile",
    "ResolvedLabelProfiles",
    "SupplierLabelProfileNotConfiguredError",
]
