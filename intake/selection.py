from collections.abc import Iterable

from intake.catalog import Receipt, ReceiptCatalog


def select_receipts(catalog: ReceiptCatalog, receipt_ids: Iterable[int]) -> tuple[Receipt, ...]:
    try:
        requested = iter(receipt_ids)
    except TypeError as error:
        raise ValueError('selection must contain receipt numbers') from error

    selected: list[Receipt] = []
    for receipt_id in requested:
        receipt = catalog.get_receipt(receipt_id)
        if receipt is None:
            raise ValueError('unknown receipt in selection')
        if selected:
            previous = selected[-1].coverage
            current = receipt.coverage
            if current.specimen != previous.specimen:
                raise ValueError('selection contains different specimens')
            if current.first != previous.last + 1:
                raise ValueError('selection is reversed, overlapping or has missing beats')
        selected.append(receipt)
    if not selected:
        raise ValueError('selection is empty')
    return tuple(selected)
