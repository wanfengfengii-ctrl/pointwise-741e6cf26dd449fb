from dataclasses import dataclass

from source.series import MeasurementRevision, Sample, require_beat, require_specimen


@dataclass(frozen=True)
class ShiftWindow:
    specimen: str
    first: int
    last: int

    def __post_init__(self) -> None:
        require_specimen(self.specimen)
        require_beat(self.first)
        require_beat(self.last)
        if self.first > self.last:
            raise ValueError('shift window is reversed')


def require_covered_window(
    revision: MeasurementRevision, window: ShiftWindow
) -> tuple[Sample, ...]:
    if revision.specimen != window.specimen:
        raise ValueError('measurement revision belongs to a different specimen')
    samples = tuple(
        sample for sample in revision.samples if window.first <= sample.beat <= window.last
    )
    if len(samples) != window.last - window.first + 1:
        raise ValueError('shift window has missing original beats')
    for expected, sample in enumerate(samples, start=window.first):
        if sample.beat != expected:
            raise ValueError('shift window has invalid original beat coverage')
    return samples
