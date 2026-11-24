from collections.abc import Iterable

from report.account import FatigueAccount, account_cycles
from report.cycles import CyclePoint, settle_cycles
from source.series import Sample, turning_samples


def compute_local_account(samples: Iterable[Sample]) -> FatigueAccount:
    points = (CyclePoint(sample.beat, sample.load) for sample in turning_samples(samples))
    return account_cycles(settle_cycles(points))
