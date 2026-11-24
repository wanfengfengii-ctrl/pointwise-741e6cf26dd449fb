from dataclasses import dataclass

from evidence.body import EvidenceBody, decode_evidence_body
from evidence.envelope import EvidenceEnvelope, piece_identity, read_envelope


@dataclass(frozen=True)
class VerifiedEvidence:
    original: str
    envelope: EvidenceEnvelope
    body: EvidenceBody


def verify_evidence(original: str) -> VerifiedEvidence:
    envelope = read_envelope(original)
    if envelope.piece_id != piece_identity(envelope.body):
        raise ValueError('piece identity does not match the original body')
    body = decode_evidence_body(envelope.body)
    if (envelope.shift_id, envelope.measurement_id, envelope.coverage) != (
        body.shift_id, body.measurement_id, body.coverage
    ):
        raise ValueError('envelope declarations do not match the original body')
    return VerifiedEvidence(original, envelope, body)
