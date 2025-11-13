# network/devices/switch.py

from __future__ import annotations

from typing import Dict, Optional

from network.devices.network_device import NetworkDevice, NetworkPort
from network.components.frames import EthernetFrame
from network.components.cable import Cable
from network.utils.logger import get_logger


BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"


class Switch(NetworkDevice):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._log = get_logger(f"devices.Switch.{name}")
        self._l2_enabled: bool = False
        # MAC -> port
        self._mac_table: Dict[str, NetworkPort] = {}

    def enable_l2(self, enabled: bool) -> None:
        self._l2_enabled = enabled
        if enabled:
            self._log.info("• L2 ENABLED")
        else:
            self._log.info("• L2 DISABLED")

    # ------------------------------------------------------------------ #
    # Helper: who is behind this port?
    # ------------------------------------------------------------------ #
    def _device_behind_port(self, port: NetworkPort):
        """
        Inspect the cable and return the device on the other side
        (EndDevice via NIC, or another network device).
        """
        cable: Optional[Cable] = port.cable
        if cable is None:
            return None

        # find the other endpoint on the cable
        other = cable.a if cable.b is port else cable.b

        # If it's a NIC, it should have 'owner' (EndDevice)
        owner = getattr(other, "owner", None)
        if owner is not None:
            return owner

        # If it's another NetworkPort, return its parent device
        parent = getattr(other, "parent", None)
        if parent is not None:
            return parent

        return other

    def _device_label(self, dev) -> str:
        """
        Nice printable label for a device:
          "Alex-PC (PC)", "Samsung Galaxy S24 (Phone)", "HP LaserJet Pro M404 (Printer)",
          "TP-Link Archer AX53", "Star Pro", etc.
        """
        if dev is None:
            return "unknown"

        name = getattr(dev, "friendly_name", getattr(dev, "name", repr(dev)))
        role = getattr(dev, "role", None)
        if role:
            return f"{name} ({role})"
        return name

    # ------------------------------------------------------------------ #
    # L1 receive
    # ------------------------------------------------------------------ #
    def _l1_receive(self, port: NetworkPort, bits: bytes) -> None:
        self._log.debug("· L1: signal arrived on %s (%d bytes)", port.display_name, len(bits))

        if not self._l2_enabled:
            # Pure L1 demo mode – do nothing else
            return

        try:
            frame = EthernetFrame.from_bytes(bits)
        except Exception:
            return

        self._l2_handle_frame(port, frame, bits)

    # ------------------------------------------------------------------ #
    # L2 logic
    # ------------------------------------------------------------------ #
    def _l2_handle_frame(self, in_port: NetworkPort, frame: EthernetFrame, raw: bytes) -> None:
        # MAC learning
        self._mac_table[frame.src] = in_port
        self._log.info("• L2: learned %s is on %s", frame.src, in_port.display_name)

        src_dev = self._device_behind_port(in_port)
        src_label = self._device_label(src_dev)

        if frame.dst == BROADCAST_MAC:
            # broadcast (like ARP request)
            self._log.info(
                "• L2: broadcast flood %s -> %s",
                frame.src,
                frame.dst,
            )
            self._log.info(
                "• FLOW: %s broadcast to ALL devices payload=%r",
                src_label,
                frame.payload,
            )
            self._flood(in_port, raw)
            return

        # unicast
        out_port = self._mac_table.get(frame.dst)
        if out_port is None:
            # unknown destination: flood
            self._log.info("• L2: unknown dst %s; flooding", frame.dst)
            self._log.info(
                "• FLOW: %s -> [unknown dst %s], flooding payload=%r",
                src_label,
                frame.dst,
                frame.payload,
            )
            self._flood(in_port, raw)
            return

        dst_dev = self._device_behind_port(out_port)
        dst_label = self._device_label(dst_dev)

        # Here is the NICE human log: PC -> Printer
        self._log.info(
            "• FLOW: %s -> %s payload=%r (src MAC=%s -> dst MAC=%s)",
            src_label,
            dst_label,
            frame.payload,
            frame.src,
            frame.dst,
        )

        # Actual forwarding
        self._forward(out_port, raw)

    def _flood(self, in_port: NetworkPort, raw: bytes) -> None:
        for port in self.ports:
            if port is in_port:
                continue
            if port.cable is None:
                continue
            port.cable.transmit(port, raw)

    def _forward(self, out_port: NetworkPort, raw: bytes) -> None:
        if out_port.cable is None:
            return
        out_port.cable.transmit(out_port, raw)
