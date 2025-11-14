from __future__ import annotations

from typing import Dict, Optional

from network.utils.logger import get_logger


class DHCPPool:
    """
    Simple DHCP pool config.
    """
    def __init__(self, network: str, netmask: str, gateway: str,
                 start: str, end: str):
        self.network = network
        self.netmask = netmask
        self.gateway = gateway
        self._log = get_logger("services.DHCPPool")

        self.start_ip_int = self._ip_to_int(start)
        self.end_ip_int = self._ip_to_int(end)

    @staticmethod
    def _ip_to_int(ip: str) -> int:
        parts = [int(p) for p in ip.split(".")]
        val = 0
        for p in parts:
            val = (val << 8) + p
        return val

    @staticmethod
    def _int_to_ip(value: int) -> str:
        return ".".join(str((value >> (8 * i)) & 0xFF) for i in reversed(range(4)))


class DHCPService:
    """
    Simplified DHCP service:
    DISCOVER -> ACK with IP, netmask, gateway
    """
    def __init__(self, router, pool: DHCPPool):
        self.router = router
        self.pool = pool
        self.log = get_logger("services.DHCP")
        self.leases: Dict[str, str] = {}  # MAC -> IP
        self._next_ip_int = self.pool.start_ip_int

    def handle_discover(self, mac: str) -> Optional[bytes]:
        """
        Called by router when DHCP DISCOVER is received.
        Returns DHCP_ACK payload or None if no more addresses.
        """
        ip = self._assign_ip(mac)
        if ip is None:
            self.log.warning("DHCP exhausted, cannot assign IP to %s", mac)
            return None

        self.log.info("DHCP assigned %s to MAC %s", ip, mac)

        # "DHCP_ACK|<ip>|<netmask>|<gateway>"
        payload = f"DHCP_ACK|{ip}|{self.pool.netmask}|{self.pool.gateway}"
        return payload.encode("ascii")

    def _assign_ip(self, mac: str) -> Optional[str]:
        # existing lease
        if mac in self.leases:
            return self.leases[mac]

        if self._next_ip_int > self.pool.end_ip_int:
            return None

        ip = DHCPPool._int_to_ip(self._next_ip_int)
        self.leases[mac] = ip
        self._next_ip_int += 1
        return ip
