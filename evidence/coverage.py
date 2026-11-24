from dataclasses import dataclass

from source.series import require_beat, require_specimen


@dataclass(frozen=True)
class EvidenceCoverage:
    specimen: str
    first: int
    last: int

    def __post_init__(self) -> None:
        require_specimen(self.specimen)
        require_beat(self.first)
        require_beat(self.last)
        if self.first > self.last:
            raise ValueError('evidence coverage is reversed')

    def to_wire(self) -> dict[str, str | int]:
        return {'specimen': self.specimen, 'first': self.first, 'last': self.last}


def parse_coverage(value: object) -> EvidenceCoverage:
    if not isinstance(value, dict) or value.keys() != {'specimen', 'first', 'last'}:
        raise ValueError('invalid evidence coverage declaration')
    return EvidenceCoverage(value['specimen'], value['first'], value['last'])
