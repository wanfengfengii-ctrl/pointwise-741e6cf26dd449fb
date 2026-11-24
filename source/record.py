from collections.abc import Iterable

from source.repository import MeasurementRepository
from source.series import require_specimen, validate_series


def record_measurements(
    repository: MeasurementRepository, specimen: str, rows: Iterable[object]
) -> str:
    specimen = require_specimen(specimen)
    samples = validate_series(rows)
    return repository.append_revision(specimen, samples)
