"""Data platform lab entity: datasets (derived from id)."""

from __future__ import annotations

from dataclasses import dataclass

from ._common import _edigest, _int, _pick

__all__ = [
    "DATA_CLASS",
    "SEED_DATASETS",
    "SEED_FROZEN_DATASETS",
    "Dataset",
    "derive_dataset",
]

DATA_CLASS = ("public", "internal", "confidential", "restricted")
SEED_DATASETS = ("data/dataset/curated-sales", "data/dataset/curated-ops")
SEED_FROZEN_DATASETS = ("data/dataset/frozen-1",)


@dataclass(frozen=True)
class Dataset:
    """A data-platform dataset, fully derived from its id."""

    dataset_id: str
    classification: str
    row_estimate: int
    frozen: bool

    @property
    def available(self) -> bool:
        """A frozen/quarantined dataset cannot be queried or exported."""
        return not self.frozen

    def summary(self) -> dict:
        return {
            "dataset_id": self.dataset_id,
            "classification": self.classification,
            "frozen": self.frozen,
        }


def derive_dataset(dataset_id: str) -> Dataset:
    did = dataset_id or "data/dataset/unknown"
    dig = _edigest("dataset", did)
    return Dataset(
        dataset_id=did,
        classification=_pick(dig, DATA_CLASS),
        row_estimate=_int(dig, 0, 1000000, offset=8),
        frozen=did in SEED_FROZEN_DATASETS,
    )
