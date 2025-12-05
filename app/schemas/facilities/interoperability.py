from pydantic import BaseModel
from typing import Optional
from enum import Enum

class AuthenticationType(str, Enum):
    OAuth2 = "OAuth2"
    Basic = "Basic"
    Smart = "Smart"
    NoneType = "None"


class FHIRConfiguration(BaseModel):
    fhir_base_url: Optional[str] = None
    authentication_type: Optional[AuthenticationType] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None


class MessageFeeds(BaseModel):
    adt: bool = False
    orm: bool = False
    oru: bool = False
    dft: bool = False

class HL7Configuration(BaseModel):
    mllp_host: Optional[str] = None
    mllp_port: Optional[int] = None
    enable_tls: bool = False
    message_feeds: Optional[MessageFeeds] = None


class DocumentExchange(BaseModel):
    enable_cdd_excha: bool = False
    enable_xds_documents: bool = False


class HealthInformationExchanges(BaseModel):
    carequality : bool = False
    commonwell : bool = False
    tefca : bool = False
    hie_name: Optional[str] = None
    

class Organisation_identifier(BaseModel):
    npi: Optional[str] = None
    tax_id: Optional[str] = None
    cms_facility_id: Optional[str] = None
    organization_oid: Optional[str] = None


class InteroperabilitySchema(BaseModel):
    fhir_configuration: Optional[FHIRConfiguration] = None
    hl7_configuration: Optional[HL7Configuration] = None
    document_exchange: Optional[DocumentExchange] = None
    health_information_exchanges: Optional[HealthInformationExchanges] = None
    organisation_identifier: Optional[Organisation_identifier] = None