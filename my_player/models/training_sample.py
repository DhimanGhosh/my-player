from dataclasses import dataclass


@dataclass
class Sample:
    query: str
    doc: str
    label: float
