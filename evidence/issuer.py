from evidence.archive import EvidenceArchive
from evidence.body import build_dwell_body, build_evidence_body, encode_dwell_body, encode_evidence_body
from evidence.coverage import EvidenceCoverage
from evidence.envelope import make_envelope
from shift.repository import ShiftRepository
from shift.window import require_covered_window
from source.repository import MeasurementRepository


def issue_evidence(
    measurements: MeasurementRepository,
    shifts: ShiftRepository,
    archive: EvidenceArchive,
    shift_id: str,
) -> str:
    original = archive.get_by_shift(shift_id)
    if original is not None:
        return original

    frozen = shifts.get_frozen(shift_id)
    if frozen is None:
        raise ValueError('unknown frozen shift')
    revision = measurements.get_revision(frozen.measurement_id)
    if revision is None:
        raise ValueError('frozen shift has no measurement revision')
    samples = require_covered_window(revision, frozen.window)
    window = frozen.window
    coverage = EvidenceCoverage(window.specimen, window.first, window.last)
    body = build_evidence_body(
        frozen.shift_id, revision.revision_id, coverage, samples, frozen.account
    )
    original = make_envelope(
        encode_evidence_body(body), frozen.shift_id, revision.revision_id, coverage
    )
    return archive.put_original(original)


def issue_dwell_evidence(
    measurements: MeasurementRepository,
    shifts: ShiftRepository,
    archive: EvidenceArchive,
    shift_id: str,
) -> str:
    original = archive.get_dwell_by_shift(shift_id)
    if original is not None:
        return original

    frozen = shifts.get_frozen(shift_id)
    if frozen is None:
        raise ValueError('unknown frozen shift')
    revision = measurements.get_revision(frozen.measurement_id)
    if revision is None:
        raise ValueError('frozen shift has no measurement revision')
    samples = require_covered_window(revision, frozen.window)
    window = frozen.window
    coverage = EvidenceCoverage(window.specimen, window.first, window.last)
    body = build_dwell_body(
        frozen.shift_id, revision.revision_id, coverage, samples, frozen.account
    )
    original = make_envelope(
        encode_dwell_body(body), frozen.shift_id, revision.revision_id, coverage, version=2
    )
    return archive.put_dwell_original(original)
