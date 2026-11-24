from collections.abc import Callable, Iterable

from evidence.body import decode_evidence_body
from evidence.envelope import read_envelope
from intake.catalog import ReceiptCatalog
from intake.selection import select_receipts
from report.account import account_cycles
from report.cycles import CyclePoint, settle_cycles
from report.publication import PublishedReport, publish_report
from report.repository import ReportRepository, StoredReport
from source.series import turning_samples


def assemble_report(
    catalog: ReceiptCatalog,
    repository: ReportRepository,
    receipt_ids: Iterable[int],
    *,
    after_report_write: Callable[[StoredReport], None] | None = None,
) -> PublishedReport:
    """Settle one continuous record using immutable center receipts only."""
    if repository.connection is not catalog.connection:
        raise ValueError('reports and receipts must use the same center connection')
    receipts = select_receipts(catalog, receipt_ids)
    bodies = (decode_evidence_body(read_envelope(receipt.original).body) for receipt in receipts)
    candidates = (point for body in bodies for point in body.points)
    turns = turning_samples(candidates)
    points = (CyclePoint(turn.beat, turn.load) for turn in turns)
    account = account_cycles(settle_cycles(points))
    return publish_report(repository, account, receipts, after_report_write=after_report_write)
