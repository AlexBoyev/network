from __future__ import annotations

import time

from network.components.cable import Cable
from network.devices.switch import Switch
from network.devices.router import Router
from network.devices.end_device import EndDevice
from network.services.dhcp import DHCPPool
from network.utils.config_loader import load_device_config
from network.utils.logger import get_logger


log = get_logger("netdemo.driver")


def _apply_router_metadata_from_yaml(router: Router, router_cfg: dict) -> None:
    """
    Set friendly_name/model from YAML.
    Interface-specific stuff (MAC/IP/DHCP) is applied later
    when we know which port is lan1/lan2 etc.
    """
    router.friendly_name = router_cfg.get("friendly_name", router.name)
    router.model = router_cfg.get("model")


def _apply_switch_metadata_from_yaml(sw: Switch, sw_cfg: dict) -> None:
    sw.friendly_name = sw_cfg.get("friendly_name", sw.name)
    sw.model = sw_cfg.get("model")


def _apply_enddevice_metadata_from_yaml(dev: EndDevice, dev_cfg: dict) -> None:
    dev.role = dev_cfg.get("role", dev.role)
    dev.friendly_name = dev_cfg.get("friendly_name", dev.friendly_name)
    dev.model = dev_cfg.get("model", dev.model)

    mac = dev_cfg.get("mac")
    if mac:
        dev.nic.mac = mac
        dev.log.info("• L2 config: overriding NIC MAC to %s from YAML", mac)


def _ip_to_int(ip: str) -> int:
    parts = [int(p) for p in ip.split(".")]
    v = 0
    for p in parts:
        v = (v << 8) + p
    return v


def _int_to_ip(v: int) -> str:
    return ".".join(str((v >> (8 * i)) & 0xFF) for i in reversed(range(4)))


def build_topology():
    """
    Build the full topology according to devices.yaml:

      home_router.lan1 -> office_switch.wan
      home_router.lan2 -> living_room_switch.wan

      office_switch.lan1 -> phone_1
      office_switch.lan2 -> office_pc
      office_switch.lan3 -> printer

      living_room_switch.lan1 -> phone_2
      living_room_switch.lan2 -> tv
    """
    log.info("• • Starting network demo driver...")
    log.info("• • === PHASE 1: Load config & build L1 topology ===")

    cfg = load_device_config()

    # ---------- Router ----------
    router_cfg = cfg["router"]
    router = Router(router_cfg["name"])
    _apply_router_metadata_from_yaml(router, router_cfg)

    # ---------- Switches ----------
    switches_cfg = cfg.get("switches", {})
    office_sw_cfg = switches_cfg.get("office_switch", {})
    living_sw_cfg = switches_cfg.get("living_room_switch", {})

    office_switch = Switch("office_switch")
    _apply_switch_metadata_from_yaml(office_switch, office_sw_cfg)

    living_switch = Switch("living_room_switch")
    _apply_switch_metadata_from_yaml(living_switch, living_sw_cfg)

    # ---------- Cables: router <-> switches ----------
    # Router lan1 <-> office_switch wan
    cable_r_office = Cable()
    r_port_lan1 = router.add_port(cable_r_office)
    sw_office_wan_port = office_switch.add_port(cable_r_office)

    # Router lan2 <-> living_room_switch wan
    cable_r_living = Cable()
    r_port_lan2 = router.add_port(cable_r_living)
    sw_living_wan_port = living_switch.add_port(cable_r_living)

    # ---------- End devices on office_switch ----------
    end_cfg = cfg["enddevices"]

    cable_phone_1 = Cable()
    sw_office_lan1 = office_switch.add_port(cable_phone_1)
    phone_1 = EndDevice("phone_1", cable_phone_1)
    _apply_enddevice_metadata_from_yaml(phone_1, end_cfg["phone_1"])

    cable_office_pc = Cable()
    sw_office_lan2 = office_switch.add_port(cable_office_pc)
    office_pc = EndDevice("office_pc", cable_office_pc)
    _apply_enddevice_metadata_from_yaml(office_pc, end_cfg["office_pc"])

    cable_printer = Cable()
    sw_office_lan3 = office_switch.add_port(cable_printer)
    printer = EndDevice("printer", cable_printer)
    _apply_enddevice_metadata_from_yaml(printer, end_cfg["printer"])

    # ---------- End devices on living_room_switch ----------
    cable_phone_2 = Cable()
    sw_living_lan1 = living_switch.add_port(cable_phone_2)
    phone_2 = EndDevice("phone_2", cable_phone_2)
    _apply_enddevice_metadata_from_yaml(phone_2, end_cfg["phone_2"])

    cable_tv = Cable()
    sw_living_lan2 = living_switch.add_port(cable_tv)
    tv = EndDevice("tv", cable_tv)
    _apply_enddevice_metadata_from_yaml(tv, end_cfg["tv"])

    # ---------- Power ON devices ----------
    log.info("• • === PHASE 2: Power on devices (L1 ready) ===")
    router.turn_on()
    office_switch.turn_on()
    living_switch.turn_on()

    for dev in (phone_1, office_pc, printer, phone_2, tv):
        dev.turn_on()

    # ---------- L2: enable switching ----------
    log.info("• • === PHASE 3: Enable L2 switching on all switches ===")
    # IMPORTANT: your Switch.enable_l2 requires 'enabled' argument
    office_switch.enable_l2(True)
    living_switch.enable_l2(True)

    # ---------- L3: configure router interfaces (static from YAML) ----------
    log.info("• • === PHASE 4: Configure router L3 interfaces from YAML ===")

    iface_cfg = router_cfg.get("interfaces", {})

    # Map router technical port names to logical YAML interfaces.
    # We know from the order we wired:
    #   r_port_lan1 -> lan1
    #   r_port_lan2 -> lan2
    port_to_iface_name = {
        r_port_lan1.name: "lan1",
        r_port_lan2.name: "lan2",
        # lan3/lan4 exist in YAML but are unused (no cables) in this topology
    }

    for port_name, iface_name in port_to_iface_name.items():
        iface_yaml = iface_cfg.get(iface_name)
        if not iface_yaml:
            log.warning("Router YAML has no config for interface %s", iface_name)
            continue

        iface = router.interfaces.get(port_name)
        if iface is None:
            log.error("Router %s: no interface for port %s", router.name, port_name)
            continue

        # Override interface MAC from YAML
        mac_from_yaml = iface_yaml.get("mac")
        if mac_from_yaml:
            iface.mac = mac_from_yaml
            router._log.info(
                "Router %s: overriding MAC on %s (%s) to %s from YAML",
                getattr(router, "friendly_name", router.name),
                port_name,
                iface.name,
                mac_from_yaml,
            )

        ip = iface_yaml.get("ip")
        netmask = iface_yaml.get("netmask")
        if ip and netmask:
            router.configure_interface(port_name, ip, netmask)

    # ---------- L3: attach DHCP (for lan1 only, with current DHCPService) ----------
    log.info("• • === PHASE 5: Attach DHCP service for Office LAN (lan1) ===")

    lan1_cfg = iface_cfg.get("lan1")
    if lan1_cfg:
        gw_ip = lan1_cfg["ip"]
        netmask = lan1_cfg["netmask"]
        dhcp_start = lan1_cfg["dhcp_start"]
        dhcp_end = lan1_cfg["dhcp_end"]

        ip_int = _ip_to_int(gw_ip)
        mask_int = _ip_to_int(netmask)
        network_int = ip_int & mask_int
        network_str = _int_to_ip(network_int)

        pool = DHCPPool(
            network=network_str,
            netmask=netmask,
            gateway=gw_ip,
            start=dhcp_start,
            end=dhcp_end,
        )
        router.attach_dhcp_service(pool)
    else:
        log.warning("No lan1 config found in router YAML; DHCP not attached")

    topology = {
        "router": router,
        "office_switch": office_switch,
        "living_switch": living_switch,
        "devices": {
            "phone_1": phone_1,
            "office_pc": office_pc,
            "printer": printer,
            "phone_2": phone_2,
            "tv": tv,
        },
    }
    return topology


def simple_l3_demo(topology: dict) -> None:
    """
    Small L3 demo:
      - Office devices obtain IP via DHCP (lan1 / 10.0.10.x).
      - Office PC sends an IP packet to printer.
    """
    devices = topology["devices"]
    phone_1 = devices["phone_1"]
    office_pc = devices["office_pc"]
    printer = devices["printer"]

    log.info("• • === PHASE 6: DHCP for Office LAN devices (lan1 only) ===")
    for dev in (phone_1, office_pc, printer):
        dev.request_ip_via_dhcp()
        time.sleep(0.1)

    log.info("• • === PHASE 7: L3 test — office_pc -> printer ===")
    if printer.ip_address:
        office_pc.send_ip_packet(
            printer.ip_address,
            b"Hello from office_pc to printer",
        )
    else:
        log.warning("Printer has no IP yet; skipping L3 send test")


def main() -> None:
    topology = build_topology()
    simple_l3_demo(topology)


if __name__ == "__main__":
    main()
