from __future__ import annotations

import random
from typing import TYPE_CHECKING

from network.components.frames import EthernetFrame
from network.interfaces.l1 import L1Endpoint
from network.components.cable import Cable
from network.utils.logger import get_logger, log_call

if TYPE_CHECKING:
    from network.devices.end_device import EndDevice


class NIC(L1Endpoint):
    """
    Network Interface Card for an endpoint device.
    Owns the MAC address and connects to a Cable.
    """
    def __init__(self, owner: "EndDevice", cable: Cable) -> None:
        self.owner = owner
        self.cable = cable
        self._log = get_logger(f"devices.NIC.{owner.name}")
        self.mac = self._generate_mac()
        self._log.info("NIC created with MAC %s", self.mac)
        cable.plug(self)

    @property
    def name(self) -> str:
        return f"{self.owner.name}.nic"

    def _generate_mac(self) -> str:
        # Locally administered unicast MAC (starts with 0x02)
        octets = [0x02] + [random.randint(0x00, 0xFF) for _ in range(5)]
        return ":".join(f"{o:02x}" for o in octets)

    @log_call()
    def send_bits(self, bits: bytes) -> None:
        if not self.cable:
            self._log.warning("No cable attached, cannot send")
            return
        self._log.info("TX raw bits (%d bytes)", len(bits))
        self.cable.transmit(self, bits)

    @log_call()
    def send_frame(self, dst_mac: str, payload: bytes) -> None:
        frame = EthernetFrame(dst_mac, self.mac, payload)
        data = frame.to_bytes()
        self._log.info("TX frame %s -> %s (%d bytes payload)", self.mac, dst_mac, len(payload))
        self.send_bits(data)

    def l1_receive(self, bits: bytes) -> None:
        """
        Called by Cable when bits arrive; pass them up to the owner EndDevice.
        """
        self._log.info("RX bits (%d bytes)", len(bits))
        self.owner.l1_receive(bits)
