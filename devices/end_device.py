from __future__ import annotations

from typing import Optional

from network.utils.logger import get_logger
from network.components.frames import EthernetFrame
from network.devices.nic import NIC

# Optional decorator you seem to use for START/END debug logs
try:
    from network.utils.decorators import log_call
except ImportError:  # safe fallback if not present
    def log_call(func):
        return func


class EndDevice:
    """
    Simple end device (PC / phone / printer / etc).

    The driver can (optionally) set:
        self.role          -> "PC", "Phone", "Printer", ...
        self.friendly_name -> "Alex-PC", "Samsung Galaxy S24", "HP LaserJet Pro", ...
        self.model         -> model string (for info only)
    """

    def __init__(self, name: str, cable):
        """
        :param name: internal name, e.g. 'host1', 'host2', 'host3'
        :param cable: Cable object connected to the switch
        """
        self.name: str = name
        self.log = get_logger(f"devices.EndDevice.{name}")

        # Default metadata – driver (YAML) can overwrite these
        self.role: str = "EndDevice"
        self.friendly_name: str = name
        self.model: Optional[str] = None

        self.powered_on: bool = False

        # IMPORTANT: match NIC signature: NIC(owner, cable)
        self.nic = NIC(self, cable)

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    @property
    def display_name(self) -> str:
        """
        Human-readable name for logs.

        Examples:
            "Alex-PC (PC)"
            "Samsung Galaxy S24 (Phone)"
            "HP LaserJet Pro M404 (Printer)"
        """
        if self.role:
            return f"{self.friendly_name} ({self.role})"
        return self.friendly_name

    # ------------------------------------------------------------------ #
    #  Power control
    # ------------------------------------------------------------------ #
    def turn_on(self) -> None:
        self.powered_on = True
        self.log.info("• Power ON")

    def turn_off(self) -> None:
        self.powered_on = False
        self.log.info("• Power OFF")

    # ------------------------------------------------------------------ #
    #  L1: raw bits
    # ------------------------------------------------------------------ #
    @log_call
    def send_bits(self, data: bytes) -> None:
        """
        Send raw L1 bits (no Ethernet framing).
        Used in the L1 phase demo.
        """
        if not self.powered_on:
            self.log.warning("• Ignoring send_bits: device is OFF")
            return

        self.log.info(
            "• Host sending raw bits from %s (%d bytes)",
            self.display_name,
            len(data),
        )
        self.nic.send_bits(data)

    # This is the callback NIC will use when bits arrive from the cable.
    # Original behavior (based on your old logs) looked like: "• L1 receive: 52 bytes"
    def l1_receive(self, data: bytes) -> None:
        """
        Called by NIC on L1 receive.
        We keep the original log style and then try to decode an Ethernet frame.
        """
        # Original simple L1 log
        self.log.info("• L1 receive: %d bytes", len(data))

        # Optional extra detail with the friendly name
        self.log.debug("• L1 receive on %s: %d bytes", self.display_name, len(data))

        # Try to parse as Ethernet frame for L2
        try:
            frame = EthernetFrame.from_bytes(data)
        except Exception as exc:
            self.log.debug("• Could not parse Ethernet frame on %s: %r", self.display_name, exc)
            return

        self._handle_frame(frame)

    # ------------------------------------------------------------------ #
    #  L2: Ethernet frames
    # ------------------------------------------------------------------ #
    @log_call
    def send_frame(self, dst_mac: str, payload: bytes) -> None:
        """
        Send an Ethernet frame to dst_mac with given payload.
        """
        if not self.powered_on:
            self.log.warning("• Ignoring send_frame: device is OFF")
            return

        # Human-friendly + MAC info
        self.log.info(
            "• L2 TX: %s sending payload=%r to dst MAC %s",
            self.display_name,
            payload,
            dst_mac,
        )
        self.nic.send_frame(dst_mac, payload)

    def _handle_frame(self, frame: EthernetFrame) -> None:
        """
        Handle a received Ethernet frame at L2.
        This is where we print the nice 'PC / Phone / Printer' logs.
        """
        self.log.info(
            "• L2 RX: %s RECEIVED payload=%r (src MAC=%s -> dst MAC=%s)",
            self.display_name,
            frame.payload,
            frame.src,
            frame.dst,
        )
        # Here you can later add logic:
        # - drop if dst != my MAC and not broadcast
        # - handle ARP/IP, etc.
