from beanie import Document
from datetime import datetime

class AuditLog(Document):
    user_id: str
    action: str
    resource: str
    resource_id: str
    ip: str
    user_agent: str
    status: str
    notes: str | None = None
    timestamp: datetime

    class Settings:
        name = "audit_logs"

async def log_audit(request, action, resource, resource_id, status="success", notes=None):

    user_id = request.headers.get("X-User-ID", "anonymous")  # JWT me bhi ho sakta hai
    ip = request.client.host
    ua = request.headers.get("User-Agent", "")

    log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        ip=ip,
        user_agent=ua,
        status=status,
        notes=notes,
        timestamp=datetime.utcnow()
    )

    await log.insert()
from beanie import Document
from datetime import datetime

class AuditLog(Document):
    user_id: str
    action: str
    resource: str
    resource_id: str
    ip: str
    user_agent: str
    status: str
    notes: str | None = None
    timestamp: datetime

    class Settings:
        name = "audit_logs"

async def log_audit(user_id,request, action, resource, resource_id, status="success", notes=None):

      # JWT me bhi ho sakta hai
    ip = request.client.host
    ua = request.headers.get("User-Agent", "")

    log = AuditLog(
        user_id=user_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        ip=ip,
        user_agent=ua,
        status=status,
        notes=notes,
        timestamp=datetime.utcnow()
    )

    await log.insert()
