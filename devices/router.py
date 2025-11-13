from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random

from network.devices.network_device import NetworkDevice, NetworkPort
from network.components.frames import EthernetFrame


@dataclass
class RouterInterface:
    """
    Represents a single router interface (like a NIC on a host).
    L2 + L3 info are stored here.
    """
    # NOTE: 'name' is for human-readable logs.
    # We now usually store the port's display_name here,
    # e.g. "Star Pro->port1".
    name: str
    mac: str
    ip: Optional[str] = None
    netmask: Optional[str] = None
    arp_table: Dict[str, str] = field(default_factory=dict)  # ip -> mac

    def __repr__(self) -> str:
        return f"<RouterInterface {self.name} ip={self.ip} mac={self.mac}>"


@dataclass
class RouteEntry:
    """
    Simple routing table entry (L3 structure ready for future use).
    """
    network: str       # e.g. "10.0.0.0"
    netmask: str       # e.g. "255.255.255.0"
    next_hop: Optional[str]  # None for directly connected
    out_iface: str     # interface name, e.g. "Star Pro->port1" (human-friendly)


class Router(NetworkDevice):
    """
    Router with:
      - L1: receives raw bits on ports.
      - L2: parses Ethernet frames, behaves like a host on each interface.
      - L3: has data structures for interfaces + routing, but actual routing
            logic is not executed unless you call L3 methods from the driver.
    """
    def __init__(self, name: str) -> None:
        super().__init__(name)
        # key: port.name -> RouterInterface
        self.interfaces: Dict[str, RouterInterface] = {}
        # list of RouteEntry for future L3 use
        self.routing_table: List[RouteEntry] = []

    # ---------- L1 / port management ----------

    def _generate_interface_mac(self) -> str:
        """
        Generate a locally administered MAC address for a router interface.
        Format: 02:xx:xx:xx:xx:xx (02 = locally administered, unicast).
        """
        octets = [0x02] + [random.randint(0x00, 0xFF) for _ in range(5)]
        return ":".join(f"{o:02x}" for o in octets)

    def add_port(self, cable) -> NetworkPort:
        """
        Extend base add_port to also create a RouterInterface with its own MAC.
        """
        port = super().add_port(cable)

        mac = self._generate_interface_mac()
        # Store a nice human-readable name on the interface:
        #   e.g. "Star Pro->port1"
        iface = RouterInterface(name=port.display_name, mac=mac)
        # Still index by the stable technical port.name
        self.interfaces[port.name] = iface

        self._log.info(
            "Router %s: created interface %s with MAC %s",
            getattr(self, "friendly_name", self.name),
            iface.name,
            iface.mac,
        )

        return port

    # ---------- L3 configuration (structure only, not used in driver yet) ----------

    def add_l3_interface(self, port: NetworkPort, ip: str, netmask: str) -> None:
        """
        Assign IP + netmask to a router interface (for L3).
        Currently not used by driver (since L3 is paused), but fully available.
        """
        iface = self.interfaces.get(port.name)
        if iface is None:
            raise ValueError(f"No interface for port {port.name} on router {self.name}")

        iface.ip = ip
        iface.netmask = netmask
        self._log.info(
            "Router %s L3 interface %s configured: IP=%s mask=%s MAC=%s",
            getattr(self, "friendly_name", self.name),
            iface.name,
            ip,
            netmask,
            iface.mac,
        )

        # Optionally, add a connected route
        self.routing_table.append(
            RouteEntry(network=self._network_address(ip, netmask),
                       netmask=netmask,
                       next_hop=None,
                       out_iface=iface.name)
        )

    def add_route(self, network: str, netmask: str,
                  next_hop: Optional[str], out_iface: str) -> None:
        """
        Add a static route entry (for future L3 use).

        out_iface should usually match RouterInterface.name, e.g. "Star Pro->port1".
        """
        self.routing_table.append(
            RouteEntry(network=network,
                       netmask=netmask,
                       next_hop=next_hop,
                       out_iface=out_iface)
        )
        self._log.info(
            "Router %s: route added %s/%s via %s out %s",
            getattr(self, "friendly_name", self.name),
            network,
            netmask,
            next_hop,
            out_iface,
        )

    # dummy helper, proper implementation can come later
    def _network_address(self, ip: str, mask: str) -> str:
        # For now, just a placeholder that returns ip as "network"
        # You can implement real masking logic when you focus on L3.
        return ip

    # ---------- L1 receive: entry point from cables ----------

    def _l1_receive(self, port: NetworkPort, bits: bytes) -> None:
        """
        L1: raw bits arrived on a router port.
        Immediately attempt to interpret them as an Ethernet frame (L2).
        """
        router_label = getattr(self, "friendly_name", self.name)

        self._log.info(
            "• L1: router %s received %d bytes on %s",
            router_label,
            len(bits),
            port.display_name,
        )

        # --- L2: parse Ethernet frame ---
        try:
            frame = EthernetFrame.from_bytes(bits)
        except Exception as exc:
            self._log.warning(
                "L2: router %s got invalid Ethernet frame on %s: %r",
                router_label,
                port.display_name,
                exc,
            )
            return

        iface = self.interfaces.get(port.name)
        if iface is None:
            self._log.error(
                "Router %s: received frame on unknown port %s (%s)",
                router_label,
                port.name,
                port.display_name,
            )
            return

        dst_mac = frame.dst.lower()
        src_mac = frame.src
        payload = frame.payload

        # For now, router acts as a *listener* at L2:
        # It logs all frames, but doesn't route/forward yet.

        if dst_mac == "ff:ff:ff:ff:ff:ff":
            self._log.info(
                "L2: router %s saw broadcast frame on %s: src=%s dst=%s payload=%r",
                router_label,
                iface.name,   # human-readable interface name
                src_mac,
                frame.dst,
                payload,
            )
        else:
            self._log.info(
                "L2: router %s saw unicast frame on %s: src=%s dst=%s payload=%r",
                router_label,
                iface.name,
                src_mac,
                frame.dst,
                payload,
            )

        # NOTE:
        # When you are ready to truly use L3, you can:
        #   1) Check if dst_mac == iface.mac or broadcast
        #   2) If ARP, call self._handle_arp(...)
        #   3) If IP, call self._handle_ip(...)
        # For now we intentionally stop here to keep runtime as L1/L2 only.

    # ---------- L3 hooks (present, but not used by driver yet) ----------

    def _handle_arp(self, port: NetworkPort,
                    iface: RouterInterface,
                    frame: EthernetFrame) -> None:
        """
        Future: ARP handling (requests/replies).
        Currently not called since driver does not trigger L3 flows yet.
        """
        router_label = getattr(self, "friendly_name", self.name)
        self._log.info(
            "Router %s ARP handler stub on %s (not active yet)",
            router_label,
            iface.name,
        )

    def _handle_ip(self, port: NetworkPort,
                   iface: RouterInterface,
                   ip_payload: bytes) -> None:
        """
        Future: IP routing logic.
        Currently a stub → you can fully implement routing here later.
        """
        router_label = getattr(self, "friendly_name", self.name)
        self._log.info(
            "Router %s IP handler stub on %s (not active yet)",
            router_label,
            iface.name,
        )
