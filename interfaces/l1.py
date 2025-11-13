from typing import Protocol


class L1Endpoint(Protocol):
    """
    A thing that can sit on a cable and receive raw bits.
    NICs and switch ports implement this.
    """
    @property
    def name(self) -> str:
        ...

    def l1_receive(self, bits: bytes) -> None:
        ...
