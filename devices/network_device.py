from __future__ import annotations

from typing import List, Optional

from network.interfaces.l1 import L1Endpoint
from network.components.cable import Cable
from network.devices.device_base import DeviceBase
from network.utils.logger import get_logger


class NetworkPort(L1Endpoint):
    """
    A physical port on a network device (switch/router).
    Implements L1Endpoint so a Cable can plug into it.
    """
    def __init__(self, parent: "NetworkDevice", index: int) -> None:
        self.parent = parent
        self.index = index
        self.cable: Optional[Cable] = None
        self._log = get_logger(f"devices.{parent.name}.port{index}")

    # Internal / technical name, kept for backwards-compat if needed
    @property
    def name(self) -> str:
        return f"{self.parent.name}-p{self.index}"

    @property
    def display_name(self) -> str:
        """
        Human-friendly label for logs.

        Priority:
          1. parent.model         (e.g. "Archer AX53")
          2. parent.friendly_name (e.g. "TP-Link Archer AX53")
          3. parent.name          (e.g. "sw1" / "r1")

        Example:
          "Archer AX53->port1"
          "Star Pro->port1"
          "sw1->port2"
        """
        dev_label = (
            getattr(self.parent, "model", None)
            or getattr(self.parent, "friendly_name", None)
            or self.parent.name
        )
        return f"{dev_label}->port{self.index}"

    def __str__(self) -> str:
        # When formatted with %s, use the nice name
        return self.display_name

    def attach_cable(self, cable: Cable) -> None:
        self.cable = cable
        cable.plug(self)

    def l1_receive(self, bits: bytes) -> None:
        # use display_name instead of raw sw1-p1
        self._log.debug("L1 receive on %s (%d bytes)", self.display_name, len(bits))
        self.parent._l1_receive(self, bits)


class NetworkDevice(DeviceBase):
    """
    Base class for multi-port network devices.
    Devices can set:
        self.friendly_name
        self.model
    which are used by NetworkPort.display_name for nicer logs.
    """
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.ports: List[NetworkPort] = []

    def __str__(self) -> str:
        return self.name

    def add_port(self, cable: Cable) -> NetworkPort:
        """
        Create a new port, connect it to the cable, and return the port.
        """
        idx = len(self.ports) + 1
        port = NetworkPort(self, idx)
        self.ports.append(port)
        port.attach_cable(cable)
        # log using display_name
        self._log.info("Port %s added and connected", port.display_name)
        return port

    # Subclasses must implement this
    def _l1_receive(self, port: NetworkPort, bits: bytes) -> None:
        raise NotImplementedError
