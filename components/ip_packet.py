from dataclasses import dataclass
from network.utils.logger import log_call


@dataclass
class IPPacket:
    src_ip: str
    dst_ip: str
    payload: bytes

    @log_call()
    def to_bytes(self) -> bytes:
        # "IP|src|dst|payload"
        header = f"IP|{self.src_ip}|{self.dst_ip}|".encode("ascii")
        return header + self.payload

    @staticmethod
    @log_call()
    def from_bytes(data: bytes) -> "IPPacket":
        """
        Expect b"IP|src|dst|payload".
        """
        try:
            _, src, dst, payload = data.split(b"|", 3)
        except ValueError as e:
            raise ValueError("Not a valid IPPacket encoding") from e
        return IPPacket(src.decode("ascii"), dst.decode("ascii"), payload)
