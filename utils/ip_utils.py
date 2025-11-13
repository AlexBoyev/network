from ipaddress import IPv4Network, IPv4Address
from network.utils.logger import log_call


@log_call()
def _ip_in_prefix(ip: str, net_ip: str, prefix_len: int) -> bool:
    net = IPv4Network(f"{net_ip}/{prefix_len}", strict=False)
    return IPv4Address(ip) in net


@log_call()
def same_subnet(ip1: str, mask1: str, ip2: str, mask2: str) -> bool:
    """
    Return True if two (ip, mask) pairs belong to the same IPv4 subnet.
    """
    n1 = IPv4Network(f"{ip1}/{mask1}", strict=False)
    n2 = IPv4Network(f"{ip2}/{mask2}", strict=False)
    return n1.network_address == n2.network_address and n1.netmask == n2.netmask
