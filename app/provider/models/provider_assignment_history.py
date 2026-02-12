# from typing import Optional
# from datetime import datetime
# from beanie import Document, Link, Indexed
# from app.patients.models.patients import PatientDoc 

# class ProviderAssignmentHistory(Document):
 
#     # 🔗 Relations
#     patient: Link[PatientDoc]
#     provider: Link[Provider]
#     schedule: Optional[Link[Schedule]] = None

#     role: Optional[str] = None  # primary / secondary / surgeon / consulting

#     assigned_at: datetime = Field(default_factory=datetime.utcnow)
#     unassigned_at: Optional[datetime] = None

#     is_active: bool = True

#     class Settings:
#         name = "provider_assignment_history"
