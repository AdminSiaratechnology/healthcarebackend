from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date
from enum import Enum

# class LongTermCare(BaseModel):
#     enable_mds_reporting: bool
        

# class QualityMeasure(BaseModel):
#     enable_quality_measure: bool
#     measure_name: str
#     measure_value: float
#     reporting_period_start: date
#     reporting_period_end: date


class QualityReporting(BaseModel):
    organization_name : Optional[str]
    reporting_cadence: Optional[str]



class QualitySchema(BaseModel):
    enable_mds_reporting: bool = False
    enable_quality_measure: bool = False
    enable_infection_control_tracking: bool = False
    fall_risk_program: bool = False
    # quality_reporting: Optional[QualityReporting] = None