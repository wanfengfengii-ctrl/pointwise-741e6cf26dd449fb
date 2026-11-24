from fractions import Fraction


def parse_load(value: object) -> Fraction:
    """Parse an exact kN value from a Fraction, integer or rational text."""
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError('invalid rational load') from error
    raise ValueError('load must be a Fraction, an integer or rational text')


def encode_load(value: Fraction) -> str:
    return str(parse_load(value))
