from shift.local_account import compute_local_account
from shift.repository import FrozenShift, ShiftRepository
from shift.window import ShiftWindow, require_covered_window
from source.repository import MeasurementRepository


def freeze_shift(
    measurements: MeasurementRepository,
    shifts: ShiftRepository,
    specimen: str,
    measurement_id: str,
    first: int,
    last: int,
) -> FrozenShift:
    window = ShiftWindow(specimen, first, last)
    revision = measurements.get_revision(measurement_id)
    if revision is None:
        raise ValueError('unknown measurement revision')
    samples = require_covered_window(revision, window)
    account = compute_local_account(samples)
    return shifts.store_frozen(revision.revision_id, window, account)
