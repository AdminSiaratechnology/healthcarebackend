from beanie import Document, Link
from bson import Binary
from datetime import datetime, timezone
from pydantic import Field
from app.accounts.models.user import UserDoc
from typing import Optional

class Director_of_nursing_Docs(Document):
    user_id : Link[UserDoc] | None = None
    first_name :  Optional[Binary] = None
    
