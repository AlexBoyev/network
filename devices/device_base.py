from network.utils.logger import get_logger


class DeviceBase:
    """
    Base class for all devices (end hosts, switches, routers).
    Handles name, power state, and logging.
    """
    def __init__(self, name: str) -> None:
        self._name = name
        self._log = get_logger(f"devices.{self.__class__.__name__}.{name}")
        self._powered_on = False

    @property
    def name(self) -> str:
        return self._name

    def turn_on(self) -> None:
        self._powered_on = True
        self._log.info("Power ON")

    def turn_off(self) -> None:
        self._powered_on = False
        self._log.info("Power OFF")

    @property
    def is_on(self) -> bool:
        return self._powered_on
