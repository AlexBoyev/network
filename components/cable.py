# network/components/cable.py

from __future__ import annotations

from typing import Optional

from network.interfaces.l1 import L1Endpoint
from network.utils.logger import get_logger


class Cable:
    """
    Simple point-to-point L1 medium with two endpoints: a and b.
    """

    def __init__(self) -> None:
        self.a: Optional[L1Endpoint] = None
        self.b: Optional[L1Endpoint] = None
        self._log = get_logger("components.Cable")

    def plug(self, endpoint: L1Endpoint) -> None:
        """
        Attach endpoint to one side of the cable.
        """
        if self.a is None:
            self.a = endpoint
        elif self.b is None:
            self.b = endpoint
        else:
            raise RuntimeError("Cable already has two endpoints")

        endpoint_name = self._endpoint_label(endpoint)
        self._log.info("• %s plugged", endpoint_name)

    def _endpoint_label(self, endpoint: L1Endpoint) -> str:
        """
        Best-effort human label for endpoints.
        Ports will show 'Archer AX53->port4', router ports 'Star Pro->port1', etc.
        """
        if hasattr(endpoint, "display_name"):
            return endpoint.display_name
        if hasattr(endpoint, "name"):
            return endpoint.name
        return repr(endpoint)

    def transmit(self, src: L1Endpoint, bits: bytes) -> None:
        """
        Deliver bits from one endpoint to the other.
        """
        if src is self.a:
            dst = self.b
        elif src is self.b:
            dst = self.a
        else:
            # unknown sender – ignore
            return

        if dst is None:
            return

        src_label = self._endpoint_label(src)
        dst_label = self._endpoint_label(dst)

        self._log.info("• Signal %s -> %s (%d bytes)", src_label, dst_label, len(bits))
        dst.l1_receive(bits)
