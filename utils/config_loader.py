import yaml
from pathlib import Path
from network.devices.router import Router
from network.devices.switch import Switch
from network.devices.end_device import EndDevice


def load_device_config():
    config_path = Path(__file__).resolve().parent.parent / "config" / "devices.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def apply_router_metadata_from_yaml(router: Router, router_cfg: dict) -> None:
    """
    Apply router-level metadata from YAML (friendly_name, model).
    Interface-specific L3 config is handled later inside driver.
    """
    router.friendly_name = router_cfg.get("friendly_name", router.name)
    router.model = router_cfg.get("model")


def apply_switch_metadata_from_yaml(sw: Switch, sw_cfg: dict) -> None:
    """
    Apply switch-level metadata from YAML.
    Switches are pure L2 devices so only metadata is changed.
    """
    sw.friendly_name = sw_cfg.get("friendly_name", sw.name)
    sw.model = sw_cfg.get("model")


def apply_enddevice_metadata_from_yaml(dev: EndDevice, dev_cfg: dict) -> None:
    """
    Apply metadata and optional static NIC MAC from YAML to end devices.
    """
    dev.role = dev_cfg.get("role", dev.role)
    dev.friendly_name = dev_cfg.get("friendly_name", dev.friendly_name)
    dev.model = dev_cfg.get("model", dev.model)

    mac = dev_cfg.get("mac")
    if mac:
        dev.nic.mac = mac
        dev.log.info("• L2 config: overriding NIC MAC to %s from YAML", mac)