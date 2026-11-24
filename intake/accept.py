from intake.catalog import ReceiptCatalog
from intake.identity import verify_evidence


def accept_evidence(catalog: ReceiptCatalog, original: str) -> int:
    verified = verify_evidence(original)
    return catalog.register_original(verified).receipt_id
