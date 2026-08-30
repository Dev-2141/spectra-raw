"""On-disk dataset store.

Layout (under ``backend/data/datasets/<dataset_id>/``):

    meta.json          JSON metadata sidecar (DatasetMeta)
    occupancy.npy/.csv power_db.npy/.csv snr_db.npy/.csv
    threat.npy/.csv    labels.npy/.csv   emitter_id.npy

NPY is the source of truth; CSV mirrors are written for portability.
"""

from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path

import numpy as np

from ..models.core import DatasetMeta, RFEnvironmentConfig
from ..simulation.environment import RFEnvironment

_DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "datasets"

_CSV_FMT = {
    "occupancy": "%d",
    "labels": "%d",
    "emitter_id": "%d",
    "power_db": "%.4f",
    "snr_db": "%.4f",
    "threat": "%.4f",
}
_CSV_ARRAYS = {"occupancy", "power_db", "snr_db", "threat", "labels"}


class DatasetStore:
    def __init__(self, root: Path | None = None):
        self.root = root or _DATA_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    def _dir(self, dataset_id: str) -> Path:
        d = self.root / dataset_id
        if d.resolve().parent != self.root.resolve():
            raise ValueError(f"invalid dataset id: {dataset_id!r}")
        return d

    def save(self, meta: DatasetMeta, arrays: dict[str, np.ndarray]) -> DatasetMeta:
        with self._lock:
            d = self._dir(meta.dataset_id)
            d.mkdir(parents=True, exist_ok=True)
            files: dict[str, str] = {}
            for key, arr in arrays.items():
                np.save(d / f"{key}.npy", arr)
                files[f"{key}_npy"] = f"{key}.npy"
                if key in _CSV_ARRAYS:
                    np.savetxt(
                        d / f"{key}.csv",
                        arr,
                        fmt=_CSV_FMT.get(key, "%.4f"),
                        delimiter=",",
                    )
                    files[f"{key}_csv"] = f"{key}.csv"
            meta = meta.model_copy(update={"files": files})
            (d / "meta.json").write_text(
                json.dumps(meta.model_dump(), indent=2), encoding="utf-8"
            )
            return meta

    # ------------------------------------------------------------------ #
    def list(self) -> list[DatasetMeta]:
        with self._lock:
            out: list[DatasetMeta] = []
            for meta_file in sorted(self.root.glob("*/meta.json")):
                try:
                    out.append(
                        DatasetMeta.model_validate_json(
                            meta_file.read_text(encoding="utf-8")
                        )
                    )
                except Exception:  # noqa: BLE001 - skip corrupt entries
                    continue
            out.sort(key=lambda m: m.created_at, reverse=True)
            return out

    def get(self, dataset_id: str) -> DatasetMeta:
        with self._lock:
            meta_file = self._dir(dataset_id) / "meta.json"
            if not meta_file.exists():
                raise KeyError(f"dataset not found: {dataset_id}")
            return DatasetMeta.model_validate_json(
                meta_file.read_text(encoding="utf-8")
            )

    def load_arrays(self, dataset_id: str) -> dict[str, np.ndarray]:
        with self._lock:
            d = self._dir(dataset_id)
            if not (d / "meta.json").exists():
                raise KeyError(f"dataset not found: {dataset_id}")
            arrays: dict[str, np.ndarray] = {}
            for npy in d.glob("*.npy"):
                arrays[npy.stem] = np.load(npy)
            return arrays

    def delete(self, dataset_id: str) -> None:
        with self._lock:
            d = self._dir(dataset_id)
            if d.exists():
                shutil.rmtree(d)

    # ------------------------------------------------------------------ #
    def build_replay_env(self, dataset_id: str) -> RFEnvironment:
        """Rehydrate a dataset into an :class:`RFEnvironment` for simulation."""
        meta = self.get(dataset_id)
        arrays = self.load_arrays(dataset_id)
        prebuilt = {
            "emitters": [e.model_dump() for e in meta.emitters],
            "occupancy": arrays["occupancy"].astype(bool),
            "power_db": arrays["power_db"],
            "snr_db": arrays["snr_db"],
            "threat": arrays["threat"],
            "emitter_id_matrix": arrays.get("emitter_id"),
        }
        return RFEnvironment(meta.config, prebuilt=prebuilt)

    def config_for(self, dataset_id: str) -> RFEnvironmentConfig:
        return self.get(dataset_id).config

    def preview(
        self, dataset_id: str, max_rows: int = 140, max_cols: int = 96
    ) -> dict:
        """Down-sampled occupancy + mean-power grid for a heatmap thumbnail."""
        arrays = self.load_arrays(dataset_id)
        occ = arrays["occupancy"].astype(np.float32)
        power = arrays["power_db"].astype(np.float32)
        T, B = occ.shape
        rstep = max(1, -(-T // max_rows))  # ceil division -> never exceeds max_rows
        cstep = max(1, -(-B // max_cols))

        def _block_reduce(mat: np.ndarray, how: str) -> list[list[float]]:
            rows: list[list[float]] = []
            for r0 in range(0, T, rstep):
                row: list[float] = []
                block_r = mat[r0 : r0 + rstep]
                for c0 in range(0, B, cstep):
                    block = block_r[:, c0 : c0 + cstep]
                    row.append(
                        float(block.max() if how == "max" else block.mean())
                    )
                rows.append([round(v, 3) for v in row])
            return rows

        return {
            "dataset_id": dataset_id,
            "time_slots": T,
            "bands": B,
            "row_step": rstep,
            "col_step": cstep,
            "occupancy": _block_reduce(occ, "max"),
            "power_db": _block_reduce(power, "mean"),
        }


_STORE: DatasetStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> DatasetStore:
    global _STORE
    if _STORE is None:
        with _STORE_LOCK:
            if _STORE is None:
                _STORE = DatasetStore()
    return _STORE
