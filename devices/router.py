from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import random

from network.devices.network_device import NetworkDevice, NetworkPort
from network.components.frames import EthernetFrame
from network.components.ip_packet import IPPacket
from network.services.dhcp import DHCPService, DHCPPool
from network.utils.ip_utils import same_subnet
from network.utils.logger import get_logger


BROADCAST_MAC = "ff:ff:ff:ff:ff:ff"


@dataclass
class RouterInterface:
    """
    Represents a single router interface (like a NIC on a host).
    L2 + L3 info are stored here.
    """
    # We used to have "..." here as a placeholder – now it's a real dataclass.
    # name is a human-readable label, e.g. "Star Pro->port1".
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
    # NOTE: out_iface holds the *port.name* (technical) now, not the pretty label.
    out_iface: str


class Router(NetworkDevice):
    """
    Router with:
      - L1: receives raw bits on ports.
      - L2: parses Ethernet frames, behaves like a host on each interface.
      - L3: interfaces + static routing + ARP + DHCP service integration.
    """
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._log = get_logger(f"devices.Router.{name}")
        # key: port.name -> RouterInterface
        self.interfaces: Dict[str, RouterInterface] = {}
        # list of RouteEntry for L3 routing
        self.routing_table: List[RouteEntry] = []

        # Optional DHCP service (attach later from driver)
        self.dhcp: Optional[DHCPService] = None

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
        iface_name = port.display_name  # human-readable
        iface = RouterInterface(name=iface_name, mac=mac)
        # Index by the stable technical port.name
        self.interfaces[port.name] = iface

        self._log.info(
            "Router %s: interface created on %s with MAC %s",
            getattr(self, "friendly_name", self.name),
            iface.name,
            iface.mac,
        )
        return port

    # ---------- L3 interface configuration ----------

    def configure_interface(self, port_name: str, ip: str, netmask: str) -> None:
        """
        Assign IP/netmask to a router interface and add a connected route.
        port_name is the technical port.name (e.g. 'port1', 'port2').
        """
        iface = self.interfaces.get(port_name)
        if iface is None:
            self._log.error("Router %s: no interface for port %s", self.name, port_name)
            return

        iface.ip = ip
        iface.netmask = netmask

        # Add a connected route (network is derived from ip+mask).
        network = self._network_address(ip, netmask)
        self.routing_table.append(
            RouteEntry(
                network=network,
                netmask=netmask,
                next_hop=None,          # directly connected
                out_iface=port_name,    # IMPORTANT: use port.name
            )
        )

        self._log.info(
            "Router %s: configured %s ip=%s mask=%s (connected route %s/%s via %s)",
            getattr(self, "friendly_name", self.name),
            iface.name,
            ip,
            netmask,
            network,
            netmask,
            port_name,
        )

    def add_route(self, network: str, netmask: str,
                  next_hop: Optional[str], out_port_name: str) -> None:
        """
        Add a static route entry.
        out_port_name must be the technical port.name.
        """
        self.routing_table.append(
            RouteEntry(
                network=network,
                netmask=netmask,
                next_hop=next_hop,
                out_iface=out_port_name,
            )
        )
        self._log.info(
            "Router %s: route added %s/%s via %s out %s",
            getattr(self, "friendly_name", self.name),
            network,
            netmask,
            next_hop if next_hop else "direct",
            out_port_name,
        )

    # ---------- routing table helpers ----------

    def _ip_to_int(self, ip: str) -> int:
        parts = [int(p) for p in ip.split(".")]
        val = 0
        for p in parts:
            val = (val << 8) + p
        return val

    def _apply_netmask(self, ip: str, netmask: str) -> str:
        ip_int = self._ip_to_int(ip)
        mask_int = self._ip_to_int(netmask)
        net_int = ip_int & mask_int
        return ".".join(str((net_int >> (8 * i)) & 0xFF) for i in reversed(range(4)))

    def _network_address(self, ip: str, netmask: str) -> str:
        return self._apply_netmask(ip, netmask)

    # ---------- L1 receive: entry point from cables ----------

    def _l1_receive(self, port: NetworkPort, bits: bytes) -> None:
        """
        L1: raw bits arrived on a router port.
        Immediately attempt to interpret them as an Ethernet frame (L2 + L3).
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

        # Ignore frames not destined to this interface and not broadcast
        if dst_mac not in (iface.mac.lower(), BROADCAST_MAC):
            self._log.debug(
                "L2: router %s ignoring frame dst=%s on %s (iface MAC=%s)",
                router_label,
                frame.dst,
                iface.name,
                iface.mac,
            )
            return

        if dst_mac == BROADCAST_MAC:
            self._log.info(
                "L2: router %s saw broadcast frame on %s: src=%s dst=%s payload=%r",
                router_label,
                iface.name,
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

        # ---------- L3 dispatch ----------
        if payload.startswith(b"DHCP_DISCOVER|") and self.dhcp is not None:
            self._handle_dhcp_discover(iface, port, src_mac, payload)
        elif payload.startswith(b"ARP_REQ|") or payload.startswith(b"ARP_REP|"):
            self._handle_arp(port, iface, payload)
        elif payload.startswith(b"IP|"):
            self._handle_ip(port, iface, payload)
        else:
            # Unknown L3 – fine, just logged above.
            pass

    # ---------- DHCP hook ----------

    def attach_dhcp_service(self, pool: DHCPPool) -> None:
        """
        Convenience: create and attach a DHCP service to this router.
        """
        self.dhcp = DHCPService(self, pool)
        self._log.info("Router %s: DHCP service attached", self.name)

    def _handle_dhcp_discover(
        self,
        iface: RouterInterface,
        port: NetworkPort,
        src_mac: str,
        payload: bytes,
    ) -> None:
        """
        Handle DHCP DISCOVER arriving on iface/port from src_mac.
        """
        if self.dhcp is None:
            self._log.warning("DHCP DISCOVER received but no DHCP service attached")
            return

        # Payload is "DHCP_DISCOVER|<mac>"
        try:
            _, mac_from_client = payload.decode("ascii").split("|", 1)
        except ValueError:
            mac_from_client = src_mac  # fallback

        self._log.info(
            "DHCP: router %s got DISCOVER from %s (reported %s) on %s",
            self.name,
            src_mac,
            mac_from_client,
            iface.name,
        )

        ack_payload = self.dhcp.handle_discover(mac_from_client)
        if ack_payload is None:
            return

        # Send ACK back as unicast Ethernet to src_mac
        reply = EthernetFrame(dst=src_mac, src=iface.mac, payload=ack_payload)
        if port.cable:
            port.cable.transmit(port, reply.to_bytes())

    # ---------- ARP ----------

    def _handle_arp(self, port: NetworkPort,
                    iface: RouterInterface,
                    payload: bytes) -> None:
        """
        ARP handling (requests/replies) on a router interface.
        """
        try:
            msg = payload.decode("ascii")
        except Exception:
            return

        parts = msg.split("|")
        if len(parts) < 2:
            return

        if parts[0] == "ARP_REQ":
            # ARP_REQ|sender_ip|target_ip|sender_mac
            if len(parts) != 4:
                return
            _, sender_ip, target_ip, sender_mac = parts

            # Learn sender
            iface.arp_table[sender_ip] = sender_mac
            self._log.info(
                "ARP: router %s on %s learned %s -> %s",
                self.name,
                iface.name,
                sender_ip,
                sender_mac,
            )

            # If they ask for this interface IP -> reply
            if iface.ip and target_ip == iface.ip:
                reply_payload = f"ARP_REP|{iface.ip}|{iface.mac}".encode("ascii")
                reply = EthernetFrame(dst=sender_mac, src=iface.mac, payload=reply_payload)
                self._log.info(
                    "ARP: router %s replying for %s with MAC %s on %s",
                    self.name,
                    iface.ip,
                    iface.mac,
                    iface.name,
                )
                if port.cable:
                    port.cable.transmit(port, reply.to_bytes())

        elif parts[0] == "ARP_REP":
            # ARP_REP|sender_ip|sender_mac
            if len(parts) != 3:
                return
            _, sender_ip, sender_mac = parts
            iface.arp_table[sender_ip] = sender_mac
            self._log.info(
                "ARP: router %s on %s learned %s -> %s (from reply)",
                self.name,
                iface.name,
                sender_ip,
                sender_mac,
            )

    # ---------- IP routing ----------

    def _handle_ip(self, port: NetworkPort,
                   iface: RouterInterface,
                   ip_payload: bytes) -> None:
        """
        Basic IP routing:
          - Parse IP packet.
          - If destined to router (any iface IP) -> "consume".
          - Else: find outgoing interface (directly connected only).
          - Resolve ARP on that interface and forward.
        """
        router_label = getattr(self, "friendly_name", self.name)

        try:
            ip_pkt = IPPacket.from_bytes(ip_payload)
        except Exception as exc:
            self._log.warning(
                "Router %s IP handler got invalid packet on %s: %r",
                router_label,
                iface.name,
                exc,
            )
            return

        self._log.info(
            "Router %s L3 RX: %s -> %s on %s",
            router_label,
            ip_pkt.src_ip,
            ip_pkt.dst_ip,
            iface.name,
        )

        # Is it for the router itself?
        for if2 in self.interfaces.values():
            if if2.ip == ip_pkt.dst_ip:
                self._log.info(
                    "Router %s: IP packet destined to router (%s), consuming",
                    router_label,
                    if2.ip,
                )
                return

        # Find outgoing interface (simple directly-connected check)
        out_port_name: Optional[str] = None
        out_iface: Optional[RouterInterface] = None

        for port_name, if2 in self.interfaces.items():
            if if2.ip and if2.netmask:
                if same_subnet(ip_pkt.dst_ip, if2.netmask, if2.ip, if2.netmask):
                    out_port_name = port_name
                    out_iface = if2
                    break

        if out_iface is None or out_port_name is None:
            self._log.warning(
                "Router %s: no route to %s, dropping",
                router_label,
                ip_pkt.dst_ip,
            )
            return

        # Determine next hop (no static next-hop support yet → directly connected)
        target_ip = ip_pkt.dst_ip

        # ARP resolution on outgoing iface
        dst_mac = out_iface.arp_table.get(target_ip)
        out_port = self._get_port_by_name(out_port_name)
        if out_port is None:
            self._log.error(
                "Router %s: cannot find port %s for forwarding",
                router_label,
                out_port_name,
            )
            return

        if dst_mac is None:
            self._log.info(
                "Router %s: need ARP for %s on %s, sending ARP request",
                router_label,
                target_ip,
                out_iface.name,
            )
            self._send_arp_request(out_port, out_iface, target_ip, sender_ip=ip_pkt.src_ip)
            dst_mac = out_iface.arp_table.get(target_ip)

        if dst_mac is None:
            self._log.warning(
                "Router %s: ARP still unresolved for %s, dropping packet",
                router_label,
                target_ip,
            )
            return

        # Forward IP packet
        fwd_frame = EthernetFrame(dst=dst_mac, src=out_iface.mac, payload=ip_payload)
        self._log.info(
            "Router %s: forwarding IP %s -> %s out %s (MAC %s)",
            router_label,
            ip_pkt.src_ip,
            ip_pkt.dst_ip,
            out_iface.name,
            dst_mac,
        )
        if out_port.cable:
            out_port.cable.transmit(out_port, fwd_frame.to_bytes())

    # ---------- helpers ----------

    def _get_port_by_name(self, port_name: str) -> Optional[NetworkPort]:
        for p in self.ports:
            if p.name == port_name:
                return p
        return None

    def _send_arp_request(
        self,
        out_port: NetworkPort,
        out_iface: RouterInterface,
        target_ip: str,
        sender_ip: str,
    ) -> None:
        """
        Send an ARP request from router out_iface to discover MAC for target_ip.
        """
        if not out_iface.ip:
            return
        payload = f"ARP_REQ|{sender_ip}|{target_ip}|{out_iface.mac}".encode("ascii")
        frame = EthernetFrame(dst=BROADCAST_MAC, src=out_iface.mac, payload=payload)
        if out_port.cable:
            out_port.cable.transmit(out_port, frame.to_bytes())
