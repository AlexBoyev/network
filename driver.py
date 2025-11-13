from __future__ import annotations

from pathlib import Path
import yaml

from network.utils.logger import get_logger
from network.components.cable import Cable
from network.devices.end_device import EndDevice
from network.devices.switch import Switch
from network.devices.router import Router


# ---------------------------------------------------------------------------
# Config loader (YAML)
# ---------------------------------------------------------------------------

def load_device_config() -> dict:
    """
    Load device metadata (roles, friendly names, models, etc.) from YAML.

    Expected path: network/config/devices.yaml (relative to this driver.py).
    """
    config_path = Path(__file__).resolve().parent / "config" / "devices.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# L1: build topology + raw signals
# ---------------------------------------------------------------------------

def activate_l1():
    """
    PHASE 1: Build topology, power devices, and test L1 (raw bits only).
    Returns objects so we can continue with L2 (and L3 in the future).
    """
    log = get_logger("driver")
    cfg = load_device_config()

    log.info("• === PHASE 1: Activate L1 (Physical Layer) ===")

    # --- Topology: 3 hosts + switch + router uplink ---
    log.info("• Building topology (cables, switch, hosts, router)...")
    c1 = Cable()
    c2 = Cable()
    c3 = Cable()
    cu = Cable()  # uplink to router

    # SWITCH
    sw_cfg = cfg["switch"]
    sw = Switch(sw_cfg["name"])  # internal name, e.g. "sw1"
    # attach some friendly metadata (Python will happily allow new attrs)
    sw.friendly_name = sw_cfg.get("friendly_name", sw_cfg["name"])
    sw.model = sw_cfg.get("model", "")

    sw.add_port(c1)   # sw1-p1
    sw.add_port(c2)   # sw1-p2
    sw.add_port(c3)   # sw1-p3
    sw.add_port(cu)   # sw1-p4 (uplink to router)

    # END DEVICES (hosts)
    ed_cfg = cfg["enddevices"]

    # host1 = PC
    h1 = EndDevice("host1", c1)
    h1.role = ed_cfg["host1"].get("role", "EndDevice")
    h1.friendly_name = ed_cfg["host1"].get("friendly_name", "host1")
    h1.model = ed_cfg["host1"].get("model")

    # host2 = Phone
    h2 = EndDevice("host2", c2)
    h2.role = ed_cfg["host2"].get("role", "EndDevice")
    h2.friendly_name = ed_cfg["host2"].get("friendly_name", "host2")
    h2.model = ed_cfg["host2"].get("model")

    # host3 = Printer
    h3 = EndDevice("host3", c3)
    h3.role = ed_cfg["host3"].get("role", "EndDevice")
    h3.friendly_name = ed_cfg["host3"].get("friendly_name", "host3")
    h3.model = ed_cfg["host3"].get("model")

    # ROUTER
    r_cfg = cfg["router"]
    r1 = Router(r_cfg["name"])
    r1.friendly_name = r_cfg.get("friendly_name", r_cfg["name"])
    r1.model = r_cfg.get("model")
    r1_uplink_port = r1.add_port(cu)   # r1-p1

    # --- Power on devices ---
    log.info("• Powering on all devices...")
    for d in (h1, h2, h3, sw, r1):
        d.turn_on()

    # --- Human-readable summary of the lab ---
    log.info(
        "• Device roles:\n"
        "    - host1: %s (%s, model=%s)\n"
        "    - host2: %s (%s, model=%s)\n"
        "    - host3: %s (%s, model=%s)\n"
        "    - switch: %s (model=%s)\n"
        "    - router: %s (model=%s)",
        h1.friendly_name, h1.role, h1.model,
        h2.friendly_name, h2.role, h2.model,
        h3.friendly_name, h3.role, h3.model,
        sw.friendly_name, sw.model,
        r1.friendly_name, r1.model,
    )

    # --- L1 signal tests: raw bits, no L2 yet ---
    log.info("• Sending raw L1 signals from PC / Phone / Printer NICs to the switch...")
    h1.send_bits(b"L1 raw test from PC")
    h2.send_bits(b"L1 raw test from Phone")
    h3.send_bits(b"L1 raw test from Printer")

    log.info(
        "• L1 summary: switch '%s' online with 4 ports (p1..p4), "
        "%s on p1, %s on p2, %s on p3, router uplink on p4; "
        "all devices ON; raw signals observed at sw1 ports; "
        "no L2 forwarding yet (stays at physical layer).",
        sw.friendly_name,
        h1.friendly_name,
        h2.friendly_name,
        h3.friendly_name,
    )

    return sw, (h1, h2, h3), r1, r1_uplink_port


# ---------------------------------------------------------------------------
# L2: enable switching + MAC learning + flooding
# ---------------------------------------------------------------------------

def activate_l2(sw: Switch, hosts: tuple[EndDevice, EndDevice, EndDevice]) -> None:
    """
    PHASE 2: Enable L2 on the switch and demonstrate MAC learning + flooding.
    Router also participates at L1/L2, but no IP/ARP routing is active yet.
    """
    log = get_logger("driver")
    log.info("• === PHASE 2: Activate L2 (Data Link Layer) ===")

    h1, h2, h3 = hosts  # h1=PC, h2=Phone, h3=Printer

    log.info(
        "• Enabling L2 on switch '%s' (MAC learning & flooding)...",
        getattr(sw, "friendly_name", sw.name),
    )
    sw.enable_l2(True)

    # --- L2 Test 1: Broadcast (like ARP request) ---
    broadcast = "ff:ff:ff:ff:ff:ff"
    log.info(
        "• L2 test #1: %s (%s) broadcasts 'who-is-everyone?' to the LAN "
        "(dst=%s, src MAC=%s)",
        h1.friendly_name,
        h1.role,
        broadcast,
        h1.nic.mac,
    )
    h1.send_frame(broadcast, b"who-is-everyone?")

    # Optional: high-level flow line for the broadcast
    log.info("• FLOW: %s (%s) -> ALL DEVICES (broadcast)", h1.friendly_name, h1.role)

    # --- L2 Test 2: PC -> Phone (unicast; switch floods first time) ---
    dst_mac_h2 = h2.nic.mac
    log.info(
        "• L2 test #2: %s (%s) sends 'hello phone' to %s (%s) "
        "[src MAC=%s -> dst MAC=%s]",
        h1.friendly_name,
        h1.role,
        h2.friendly_name,
        h2.role,
        h1.nic.mac,
        dst_mac_h2,
    )
    h1.send_frame(dst_mac_h2, b"hello phone")

    # <<< NEW: ultra-simple human flow line
    log.info(
        "• FLOW: %s -> %s",
        h1.role or h1.friendly_name,   # "PC"
        h2.role or h2.friendly_name,   # "Phone"
    )

    # --- L2 Extra Test: PC -> Printer (unicast) ---
    dst_mac_h3 = h3.nic.mac
    log.info(
        "• L2 extra: %s (%s) sends 'hello printer' to %s (%s) "
        "[src MAC=%s -> dst MAC=%s]",
        h1.friendly_name,
        h1.role,
        h3.friendly_name,
        h3.role,
        h1.nic.mac,
        dst_mac_h3,
    )
    h1.send_frame(dst_mac_h3, b"hello printer")

    # <<< NEW: THIS is the line you asked for
    log.info(
        "• FLOW: %s -> %s",
        h1.role or h1.friendly_name,   # "PC"
        h3.role or h3.friendly_name,   # "Printer"
    )

    log.info("• L2 testing complete (broadcast + unknown-unicast flooding + MAC learning).")



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> None:
    log = get_logger("driver")
    log.info("• Starting network demo driver...")
    sw, hosts, r1, r1_uplink_port = activate_l1()
    activate_l2(sw, hosts)
    # L3 is PAUSED for now:
    # activate_l3(sw, hosts, r1, r1_uplink_port)
    log.info("• Demo finished.")


if __name__ == "__main__":
    run()
