from __future__ import annotations

from typing import Optional, Dict

from network.utils.logger import get_logger
from network.components.frames import EthernetFrame
from network.devices.nic import NIC
from network.components.ip_packet import IPPacket
from network.utils.ip_utils import same_subnet

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

        # Power
        self.powered_on: bool = False

        # NIC (L1/L2)
        self.nic = NIC(self, cable)

        # ---------- L3 state ----------
        self.ip_address: Optional[str] = None
        self.netmask: Optional[str] = None
        self.default_gateway: Optional[str] = None
        # ARP cache: ip -> mac
        self.arp_table: Dict[str, str] = {}

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
    #  L3 configuration + DHCP
    # ------------------------------------------------------------------ #
    def configure_ip(self, ip: str, netmask: str, gateway: str) -> None:
        """
        Set IP configuration (typically called from DHCP client logic).
        """
        self.ip_address = ip
        self.netmask = netmask
        self.default_gateway = gateway
        self.log.info(
            "• L3 config: %s IP=%s mask=%s gw=%s",
            self.display_name,
            ip,
            netmask,
            gateway,
        )

    @log_call
    def request_ip_via_dhcp(self) -> None:
        """
        Very simple DHCP client:
        - Broadcasts a DHCP_DISCOVER payload.
        - Router's DHCP service should reply with DHCP_ACK.
        """
        if not self.powered_on:
            self.log.warning("• Ignoring DHCP request: device is OFF")
            return

        payload = f"DHCP_DISCOVER|{self.nic.mac}".encode("ascii")
        self.log.info("• L3 DHCP: %s sending discover", self.display_name)
        self.nic.send_frame("ff:ff:ff:ff:ff:ff", payload)

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
            "• L1 TX: %s sending raw bits (%d bytes)",
            self.display_name,
            len(data),
        )
        self.nic.send_bits(data)

    def l1_receive(self, data: bytes) -> None:
        """
        Called by NIC on L1 receive.
        We keep the original log style and then try to decode an Ethernet frame.
        """
        # Original simple L1 log
        self.log.info("• L1 RX: %d bytes", len(data))
        self.log.debug("• L1 RX on %s: %d bytes", self.display_name, len(data))

        # Try to parse as Ethernet frame for L2/L3
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

        self.log.info(
            "• L2 TX: %s sending payload=%r to dst MAC %s",
            self.display_name,
            payload,
            dst_mac,
        )
        self.nic.send_frame(dst_mac, payload)

    # ------------------------------------------------------------------ #
    #  L3: IP + ARP
    # ------------------------------------------------------------------ #
    @log_call
    def send_ip_packet(self, dst_ip: str, payload: bytes) -> None:
        """
        High-level L3 send:
        1. Decide if dst is in same subnet or not.
        2. Choose next-hop IP (dst or default gateway).
        3. Resolve ARP (possibly send ARP request).
        4. Encapsulate in IPPacket, then EthernetFrame, then send via NIC.
        """
        if not self.powered_on:
            self.log.warning("• Ignoring send_ip_packet: device is OFF")
            return

        if not self.ip_address or not self.netmask:
            self.log.warning("• L3 TX: device %s has no IP config yet", self.display_name)
            return

        # Determine next hop
        if same_subnet(self.ip_address, self.netmask, dst_ip, self.netmask):
            next_hop_ip = dst_ip
        else:
            if not self.default_gateway:
                self.log.warning(
                    "• L3 TX: %s no default gateway for dst_ip=%s",
                    self.display_name,
                    dst_ip,
                )
                return
            next_hop_ip = self.default_gateway

        # Resolve ARP
        dst_mac = self.arp_table.get(next_hop_ip)
        if dst_mac is None:
            self.log.info(
                "• ARP: %s has no MAC for %s, sending ARP request",
                self.display_name,
                next_hop_ip,
            )
            self._send_arp_request(next_hop_ip)
            # In this synchronous sim, the reply may already have been processed.
            dst_mac = self.arp_table.get(next_hop_ip)

        if dst_mac is None:
            self.log.warning(
                "• ARP: %s could not resolve %s, dropping IP packet",
                self.display_name,
                next_hop_ip,
            )
            return

        # Build IP packet and send
        ip_pkt = IPPacket(src_ip=self.ip_address, dst_ip=dst_ip, payload=payload)
        self.log.info(
            "• L3 TX: %s sending IP %s -> %s via next-hop %s (MAC %s)",
            self.display_name,
            self.ip_address,
            dst_ip,
            next_hop_ip,
            dst_mac,
        )
        self.nic.send_frame(dst_mac, ip_pkt.to_bytes())

    def _send_arp_request(self, target_ip: str) -> None:
        """
        Broadcast ARP request: who has target_ip?
        Payload format (simple): b"ARP_REQ|<sender_ip>|<target_ip>|<sender_mac>"
        """
        if not self.ip_address:
            self.log.warning("• ARP: cannot send request, IP not configured")
            return

        payload = f"ARP_REQ|{self.ip_address}|{target_ip}|{self.nic.mac}".encode("ascii")
        self.log.info(
            "• ARP TX: %s requesting MAC for %s (from %s)",
            self.display_name,
            target_ip,
            self.ip_address,
        )
        self.nic.send_frame("ff:ff:ff:ff:ff:ff", payload)

    def _handle_arp_payload(self, payload: bytes) -> None:
        """
        Handle ARP request/reply at the endpoint.
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
            # Learn the sender
            self.arp_table[sender_ip] = sender_mac

            # If they ask for me, reply
            if self.ip_address and target_ip == self.ip_address:
                reply = f"ARP_REP|{self.ip_address}|{self.nic.mac}".encode("ascii")
                self.log.info(
                    "• ARP RX: %s got request for its own IP %s, replying with MAC %s",
                    self.display_name,
                    self.ip_address,
                    self.nic.mac,
                )
                self.nic.send_frame(sender_mac, reply)

        elif parts[0] == "ARP_REP":
            # ARP_REP|sender_ip|sender_mac
            if len(parts) != 3:
                return
            _, sender_ip, sender_mac = parts
            self.arp_table[sender_ip] = sender_mac
            self.log.info(
                "• ARP RX: %s learned %s -> %s",
                self.display_name,
                sender_ip,
                sender_mac,
            )

    # ------------------------------------------------------------------ #
    #  Frame handler – L2 + L3
    # ------------------------------------------------------------------ #
    def _handle_frame(self, frame: EthernetFrame) -> None:
        """
        Handle a received Ethernet frame at L2/L3.
        """
        self.log.info(
            "• L2 RX: %s RECEIVED payload=%r (src MAC=%s -> dst MAC=%s)",
            self.display_name,
            frame.payload,
            frame.src,
            frame.dst,
        )

        payload = frame.payload

        # DHCP
        if payload.startswith(b"DHCP_ACK|"):
            try:
                _, ip, mask, gw = payload.decode("ascii").split("|", 3)
            except ValueError:
                self.log.warning("• DHCP: malformed ACK payload %r", payload)
                return
            self.configure_ip(ip, mask, gw)
            return

        # ARP
        if payload.startswith(b"ARP_REQ|") or payload.startswith(b"ARP_REP|"):
            self._handle_arp_payload(payload)
            return

        # IP
        if payload.startswith(b"IP|"):
            try:
                ip_pkt = IPPacket.from_bytes(payload)
            except Exception as exc:
                self.log.warning("• L3 RX: invalid IP packet on %s: %r", self.display_name, exc)
                return

            # If it's for me -> "deliver"
            if self.ip_address == ip_pkt.dst_ip:
                self.log.info(
                    "• L3 RX: %s received IP packet %s -> %s payload=%r",
                    self.display_name,
                    ip_pkt.src_ip,
                    ip_pkt.dst_ip,
                    ip_pkt.payload,
                )
            else:
                self.log.info(
                    "• L3 RX: %s got IP packet not for me (dst=%s), ignoring for now",
                    self.display_name,
                    ip_pkt.dst_ip,
                )

        # otherwise it's just some generic L2 payload, already logged above
