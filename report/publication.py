from collections.abc import Callable
from dataclasses import dataclass

from intake.catalog import Receipt, ReceiptCatalog
from report.account import FatigueAccount
from report.provenance import bind_parents
from report.repository import ReportRepository, SigningReceipt, StoredReport


@dataclass(frozen=True)
class PublishedReport:
    report: StoredReport
    signing_receipt: SigningReceipt
    originals: tuple[Receipt, ...]


def publish_report(
    repository: ReportRepository,
    account: FatigueAccount,
    originals: tuple[Receipt, ...],
    *,
    after_report_write: Callable[[StoredReport], None] | None = None,
) -> PublishedReport:
    """Commit the selected originals' report and its signing receipt together."""
    parents = bind_parents(originals)
    connection = repository.connection
    if connection.in_transaction:
        raise RuntimeError('publication requires an idle center connection')
    with connection:
        connection.execute('BEGIN IMMEDIATE')
        report = repository.store_report(account, parents)
        if after_report_write is not None:
            after_report_write(report)
        signing_receipt = repository.store_signing_receipt(report.report_id)
    return PublishedReport(report, signing_receipt, originals)


def get_report(
    repository: ReportRepository, catalog: ReceiptCatalog, report_id: int
) -> PublishedReport | None:
    if repository.connection is not catalog.connection:
        raise ValueError('reports and receipts must use the same center connection')
    published = repository.read_published(report_id)
    if published is None:
        return None
    report, signing_receipt = published
    originals = []
    for parent in report.parents:
        original = catalog.get_receipt(parent.receipt_id)
        if original is None:
            raise ValueError('published report is missing an original receipt')
        originals.append(original)
    originals = tuple(originals)
    if bind_parents(originals) != report.parents:
        raise ValueError('original receipts conflict with the published provenance')
    return PublishedReport(report, signing_receipt, originals)
