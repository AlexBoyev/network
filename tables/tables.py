from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
from network.utils.logger import get_logger, log_call
from network.utils.ip_utils import _ip_in_prefix

@dataclass(init=False)
class ARPTable:
    entries: Dict[str, str]
    def __init__(self):
        self._log = get_logger("tables.ARPTable")
        self.entries = {}

    @log_call()
    def add(self, ip: str, mac: str) -> None:
        self.entries[ip] = mac
        self._log.info("ARP add %s -> %s", ip, mac)

    @log_call()
    def resolve(self, ip: str) -> Optional[str]:
        return self.entries.get(ip)

@dataclass(init=False)
class RoutingTable:
    routes: Dict[str, str]
    def __init__(self):
        self._log = get_logger("tables.RoutingTable")
        self.routes = {}

    @log_call()
    def add(self, cidr: str, next_hop: str) -> None:
        self.routes[cidr] = next_hop
        self._log.info("Route add %s -> %s", cidr, next_hop)

    @log_call()
    def lookup(self, dest_ip: str) -> Optional[str]:
        best = None; best_plen = -1
        for cidr, nh in self.routes.items():
            net, plen_s = cidr.split("/")
            plen = int(plen_s)
            if _ip_in_prefix(dest_ip, net, plen) and plen > best_plen:
                best, best_plen = nh, plen
        return best

@dataclass(init=False)
class NATTable:
    snat: Dict[Tuple[str,int], Tuple[str,int]]
    def __init__(self):
        self._log = get_logger("tables.NATTable")
        self.snat = {}

    @log_call()
    def create_or_get(self, priv_ip: str, priv_port: int, pub_ip: str) -> Tuple[str,int]:
        key = (priv_ip, priv_port)
        if key not in self.snat:
            self.snat[key] = (pub_ip, priv_port)
            self._log.info("SNAT %s:%d -> %s:%d", priv_ip, priv_port, pub_ip, priv_port)
        return self.snat[key]

    @log_call()
    def reverse(self, pub_ip: str, pub_port: int) -> Optional[Tuple[str,int]]:
        for (p_ip, p_port), (m_ip, m_port) in self.snat.items():
            if (m_ip, m_port) == (pub_ip, pub_port):
                return p_ip, p_port
        return None

@dataclass(init=False)
class MacTable:
    def __init__(self):
        self._log = get_logger("tables.MacTable")
        self._table: Dict[str, object] = {}

    @log_call()
    def learn(self, mac: str, port) -> None:
        self._table[mac] = port
        self._log.info("Learn %s -> %s", mac, getattr(port, "name", port))

    @log_call()
    def lookup(self, mac: str):
        return self._table.get(mac)

    @log_call()
    def __repr__(self) -> str:
        return f"MacTable({self._table})"
