# network/utils/ip_utils.py

def ip_to_int(ip: str) -> int:
    """
    Convert dotted IPv4 string to integer.
    Example: '10.0.10.1' -> 0x0A000A01
    """
    parts = [int(p) for p in ip.split(".")]
    v = 0
    for p in parts:
        v = (v << 8) + p
    return v


def int_to_ip(v: int) -> str:
    """
    Convert integer to dotted IPv4 string.
    Example: 0x0A000A01 -> '10.0.10.1'
    """
    return ".".join(str((v >> (8 * i)) & 0xFF) for i in reversed(range(4)))


def same_subnet(ip1: str, mask1: str, ip2: str, mask2: str) -> bool:
    """
    Returns True if ip1/mask1 and ip2/mask2 are in the same IPv4 subnet.
    """
    ip1_int = ip_to_int(ip1)
    ip2_int = ip_to_int(ip2)
    m1_int = ip_to_int(mask1)
    m2_int = ip_to_int(mask2)

    # If masks differ, use the stricter one (more specific) – good enough for demo
    mask_int = m1_int if m1_int >= m2_int else m2_int

    return (ip1_int & mask_int) == (ip2_int & mask_int)
