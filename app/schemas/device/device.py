from pydantic import BaseModel
from typing import Optional
from enum import Enum

class StatusEnum(str, Enum):
    Active ="Active"
    Inactive ="Inactive"
    Remove = "Remove"
    Block = "Block"
    Unblock = "Unblock"


class DeviceCreateSchema(BaseModel):
    device_name: str
    device_type: str
    platform: str
    os_version: str
    app_version: str
    battery_percentage: Optional[int] = None
    location: Optional[str] = None
    is_current_device: bool = False





# --------------------------------------------- Block All Devices ---------------------------------

class BlockAllDevicesSchema(BaseModel):
    block_current_device: bool = False



# ------------------------------------------------ Logout All Devices -----------------------------

class LogoutAllDevicesSchema(BaseModel):
    logout_current_device: bool = False
