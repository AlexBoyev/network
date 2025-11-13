from dataclasses import dataclass
from network.utils.logger import log_call


@dataclass(init=False)
class EthernetFrame:
    """
    Minimal Ethernet frame model: dst, src, payload.
    No VLANs, no EtherType – just enough for L2 demo.
    """
    dst: str
    src: str
    payload: bytes

    def __init__(self, dst: str, src: str, payload: bytes) -> None:
        self.dst = dst
        self.src = src
        self.payload = payload

    @log_call()
    def to_bytes(self) -> bytes:
        """
        Serialize as b"dst|src|payload".
        Super simple, purely for educational purposes.
        """
        header = f"{self.dst}|{self.src}|".encode("ascii")
        return header + self.payload

    @staticmethod
    @log_call()
    def from_bytes(data: bytes) -> "EthernetFrame":
        """
        Parse the simple 'dst|src|payload' format.
        Raises ValueError if it doesn't match.
        """
        try:
            dst, src, payload = data.split(b"|", 2)
        except ValueError as e:
            raise ValueError("Not a valid EthernetFrame encoding") from e
        return EthernetFrame(dst.decode("ascii"), src.decode("ascii"), payload)
