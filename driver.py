from __future__ import annotations

from typing import Dict, Tuple

import logging
from scrapy.utils.log import configure_logging

from network.components.cable import Cable
from network.devices.switch import Switch
from network.devices.router import Router
from network.devices.end_device import EndDevice
from network.services.dhcp import DHCPPool
from network.utils.config_loader import (
    load_device_config,
    apply_router_metadata_from_yaml,
    apply_switch_metadata_from_yaml,
    apply_enddevice_metadata_from_yaml,
)
from network.utils.ip_utils import ip_to_int, int_to_ip, same_subnet

LOG = logging.getLogger("netdemo.netdemo.driver")


# ---------------------------------------------------------------------------
# Topology builder (L1)
# ---------------------------------------------------------------------------

def build_topology(cfg: dict) -> dict:
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
    LOG.info("• • • • • • • • Building L1 topology (router, switches, NICs, cables)...")

    # ---------- Router ----------
    router_cfg = cfg["router"]
    router = Router(router_cfg["name"])
    apply_router_metadata_from_yaml(router, router_cfg)

    # ---------- Switches ----------
    switches_cfg = cfg.get("switches", {})
    office_sw_cfg = switches_cfg.get("office_switch", {})
    living_sw_cfg = switches_cfg.get("living_room_switch", {})

    office_switch = Switch("office_switch")
    apply_switch_metadata_from_yaml(office_switch, office_sw_cfg)

    living_switch = Switch("living_room_switch")
    apply_switch_metadata_from_yaml(living_switch, living_sw_cfg)

    # ---------- Cables: router <-> switches ----------

    # Router lan1 <-> office_switch wan
    cable_r_office = Cable()
    r_port_lan1 = router.add_port(cable_r_office)
    office_switch.add_port(cable_r_office)

    # Router lan2 <-> living_room_switch wan
    cable_r_living = Cable()
    r_port_lan2 = router.add_port(cable_r_living)
    living_switch.add_port(cable_r_living)

    # ---------- End devices on office_switch ----------
    end_cfg = cfg["enddevices"]

    cable_phone_1 = Cable()
    office_switch.add_port(cable_phone_1)
    phone_1 = EndDevice("phone_1", cable_phone_1)
    apply_enddevice_metadata_from_yaml(phone_1, end_cfg["phone_1"])

    cable_office_pc = Cable()
    office_switch.add_port(cable_office_pc)
    office_pc = EndDevice("office_pc", cable_office_pc)
    apply_enddevice_metadata_from_yaml(office_pc, end_cfg["office_pc"])

    cable_printer = Cable()
    office_switch.add_port(cable_printer)
    printer = EndDevice("printer", cable_printer)
    apply_enddevice_metadata_from_yaml(printer, end_cfg["printer"])

    # ---------- End devices on living_room_switch ----------
    cable_phone_2 = Cable()
    living_switch.add_port(cable_phone_2)
    phone_2 = EndDevice("phone_2", cable_phone_2)
    apply_enddevice_metadata_from_yaml(phone_2, end_cfg["phone_2"])

    cable_tv = Cable()
    living_switch.add_port(cable_tv)
    tv = EndDevice("tv", cable_tv)
    apply_enddevice_metadata_from_yaml(tv, end_cfg["tv"])

    devices: Dict[str, EndDevice] = {
        "phone_1": phone_1,
        "office_pc": office_pc,
        "printer": printer,
        "phone_2": phone_2,
        "tv": tv,
    }

    # Map router ports to logical lan names for L3 config later
    router_port_map = {
        "lan1": r_port_lan1.name,
        "lan2": r_port_lan2.name,
        # lan3/lan4 exist in YAML but are unused in this topology
    }

    LOG.info(
        "• • • • • • • • L1 topology built successfully: router=%s, switches=[%s,%s], devices=%d",
        getattr(router, "friendly_name", router_cfg["name"]),
        getattr(office_switch, "friendly_name", "office_switch"),
        getattr(living_switch, "friendly_name", "living_room_switch"),
        len(devices),
    )

    topology = {
        "router": router,
        "office_switch": office_switch,
        "living_switch": living_switch,
        "devices": devices,
        "router_port_map": router_port_map,
    }
    return topology


# ---------------------------------------------------------------------------
# PHASE 1 + 2: L1 build + power on
# ---------------------------------------------------------------------------

def start_l1() -> Tuple[dict, dict]:
    """
    Phase L1:
      - Load YAML config
      - Build topology (router, switches, devices, cables)
      - Power ON everything
    """
    LOG.info("• • • • • • • • === PHASE 1: Load config & build L1 topology ===")
    cfg = load_device_config()
    topology = build_topology(cfg)

    LOG.info("• • • • • • • • === PHASE 2: Power on devices (L1 ready) ===")
    router: Router = topology["router"]
    office_switch: Switch = topology["office_switch"]
    living_switch: Switch = topology["living_switch"]
    devices: Dict[str, EndDevice] = topology["devices"]

    router.turn_on()
    office_switch.turn_on()
    living_switch.turn_on()
    for dev in devices.values():
        dev.turn_on()

    LOG.info("• • • • • • • • L1 phase complete: physical connectivity + power are up.")
    return cfg, topology


# ---------------------------------------------------------------------------
# PHASE 3: L2 switching
# ---------------------------------------------------------------------------

def start_l2(topology: dict) -> None:
    """
    Phase L2:
      - Enable L2 switching on all switches
      - MAC learning + flooding/unicast become active
    """
    LOG.info("• • • • • • • • === PHASE 3: Enable L2 switching on all switches ===")

    office_switch: Switch = topology["office_switch"]
    living_switch: Switch = topology["living_switch"]

    # IMPORTANT: your Switch.enable_l2 requires 'enabled' argument
    office_switch.enable_l2(True)
    living_switch.enable_l2(True)

    LOG.info(
        "• • • • • • • • L2 phase complete: %s and %s now perform MAC learning and "
        "broadcast/unicast forwarding.",
        getattr(office_switch, "friendly_name", office_switch.name),
        getattr(living_switch, "friendly_name", living_switch.name),
    )


# ---------------------------------------------------------------------------
# PHASE 4–7: L3 setup + DHCP + demo
# ---------------------------------------------------------------------------

def start_l3(cfg: dict, topology: dict) -> None:
    """
    Phase L3:
      - Configure router L3 interfaces from YAML
      - Attach DHCP pool/service for Office LAN (lan1)
      - DHCP for Office LAN devices
      - ARP + IP unicast demo: office_pc -> printer
    """
    router: Router = topology["router"]
    devices: Dict[str, EndDevice] = topology["devices"]
    router_port_map: Dict[str, str] = topology["router_port_map"]

    router_cfg = cfg["router"]
    interfaces_cfg = router_cfg.get("interfaces", {})

    LOG.info("• • • • • • • • === PHASE 4: Configure router L3 interfaces from YAML ===")
    rlog = getattr(router, "_log", LOG)

    # Configure lan1 / lan2 based on the ports we wired in build_topology()
    for logical_name in ("lan1", "lan2"):
        port_name = router_port_map.get(logical_name)
        iface_yaml = interfaces_cfg.get(logical_name)
        if not port_name or not iface_yaml:
            continue

        iface = router.interfaces.get(port_name)
        if iface is None:
            rlog.error(
                "Router %s: no interface for port %s (logical %s)",
                router.name,
                port_name,
                logical_name,
            )
            continue

        mac_from_yaml = iface_yaml.get("mac")
        if mac_from_yaml:
            iface.mac = mac_from_yaml
            rlog.info(
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
            rlog.info(
                "Router %s: configured %s ip=%s mask=%s",
                getattr(router, "friendly_name", router.name),
                port_name,
                ip,
                netmask,
            )

    # ---------- DHCP attach (lan1) ----------
    LOG.info("• • • • • • • • === PHASE 5: Attach DHCP service for Office LAN (lan1) ===")

    lan1_cfg = interfaces_cfg.get("lan1")
    if not lan1_cfg:
        LOG.warning("No lan1 config found in router YAML; DHCP not attached")
        return

    gw_ip = lan1_cfg["ip"]
    netmask = lan1_cfg["netmask"]
    dhcp_start = lan1_cfg["dhcp_start"]
    dhcp_end = lan1_cfg["dhcp_end"]

    ip_int = ip_to_int(gw_ip)
    mask_int = ip_to_int(netmask)
    network_int = ip_int & mask_int
    network_str = int_to_ip(network_int)

    pool = DHCPPool(
        network=network_str,
        netmask=netmask,
        gateway=gw_ip,
        start=dhcp_start,
        end=dhcp_end,
    )
    router.attach_dhcp_service(pool)

    # ---------- DHCP for office devices ----------
    LOG.info("• • • • • • • • === PHASE 6: DHCP for Office LAN devices (lan1 only) ===")
    for name in ("phone_1", "office_pc", "printer"):
        dev = devices.get(name)
        if not dev:
            LOG.warning(
                "• • • • • • • • DHCP phase: device '%s' not found in topology; skipping DHCP for it",
                name,
            )
            continue

        dev.log.info(
            "• • L3 DHCP: %s (%s) sending discover",
            dev.friendly_name,
            dev.role,
        )
        # IMPORTANT: match your existing EndDevice API
        dev.request_ip_via_dhcp()

    LOG.info(
        "• • • • • • • • DHCP phase complete: Office LAN devices that exist in config should have IP addresses."
    )

    # ---------- Simple L3 demo: office_pc -> printer ----------
    LOG.info("• • • • • • • • === PHASE 7: L3 test — office_pc -> printer ===")
    office_pc = devices.get("office_pc")
    printer = devices.get("printer")

    if not office_pc or not printer:
        LOG.warning(
            "• • • • • • • • L3 test skipped: need both 'office_pc' and 'printer' in devices.yaml"
        )
        return

    if not printer.ip_address:
        LOG.warning("Printer has no IP yet; skipping L3 send test")
        return

    if same_subnet(
        office_pc.ip_address,
        office_pc.netmask,
        printer.ip_address,
        printer.netmask,
    ):
        LOG.debug(
            "same_subnet(%s/%s, %s/%s) -> True",
            office_pc.ip_address,
            office_pc.netmask,
            printer.ip_address,
            printer.netmask,
        )

    office_pc.send_ip_packet(
        printer.ip_address,
        b"Hello from office_pc to printer",
    )

    LOG.info("• • • • • • • • L3 phase complete: ARP + unicast IP delivery demo finished.")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def main() -> None:
    configure_logging()
    LOG.info("• • • • • • • • Starting network demo driver...")
    cfg, topology = start_l1()
    start_l2(topology)
    start_l3(cfg, topology)


if __name__ == "__main__":
    main()
