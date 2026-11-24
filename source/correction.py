from collections.abc import Iterable

from source.repository import MeasurementRepository
from source.series import Sample, require_specimen, validate_series


def correct_measurements(
    repository: MeasurementRepository,
    specimen: str,
    parent_id: str,
    changes: Iterable[object],
) -> str:
    """Apply ordered beat/load replacements to a specified immutable snapshot."""
    specimen = require_specimen(specimen)
    parent = repository.get_revision(parent_id)
    if parent is None or parent.specimen != specimen:
        raise ValueError('unknown parent revision for specimen')

    replacements = {sample.beat: sample.load for sample in validate_series(changes)}
    parent_beats = {sample.beat for sample in parent.samples}
    if replacements.keys() - parent_beats:
        raise ValueError('corrected beat is absent from the parent revision')

    corrected = tuple(
        Sample(sample.beat, replacements.get(sample.beat, sample.load))
        for sample in parent.samples
    )
    return repository.append_revision(specimen, corrected, parent_id=parent.revision_id)
