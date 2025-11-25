from dataclasses import dataclass


@dataclass
class YTCandidate:
    url: str
    title: str
    description: str
    channel: str
    duration: int  # seconds
