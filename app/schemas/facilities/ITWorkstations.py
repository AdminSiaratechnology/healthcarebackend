from pydantic import BaseModel
from typing import Optional
from enum import Enum


class PrinterRoutingMap(BaseModel):
    printer_routing_config: Optional[str] = None
    


class NetworkConfigSchema(BaseModel):
    primary_isp: Optional[str] = None
    secondary_isp: Optional[str] = None
    bandwidth: Optional[str] = None
    vpn_required: bool = False
    printer_routing_map: Optional[PrinterRoutingMap] = None


class WifiNetworkSchema(BaseModel):
    ssid: Optional[str] = None
    password: Optional[str] = None
    guest_network: bool = False


class Peripherals(BaseModel):
    printer: bool = False
    scanner: bool = False
    card_reader: bool = False
    shared_login: bool = False

class OperatingStyemType(str, Enum):
    Windows11 = "Windows11"
    Windows10 = "Windows10"
    MacOS = "MacOS"
    ChromeOS = "ChromeOS"
    Linux = "Linux"
    Ios = "Ios"
    Android = "Android"

class WorkStationSchema(BaseModel):
    work_station_code: Optional[str] = None
    location: Optional[str] = None
    os_type: Optional[OperatingStyemType] = None
    peripherals: Optional[Peripherals] = None



class DeviceType(str, Enum):
    Tablet = "Tablet"
    Laptop = "Laptop"
    Desktop = "Desktop"
    

class DeviceInventorySchema(BaseModel):
    device_type: Optional[DeviceType] = None
    count: Optional[int] = None
    operating_system: Optional[OperatingStyemType] = None
   