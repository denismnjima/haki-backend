from pydantic import BaseModel, EmailStr, constr
from datetime import date, time, datetime
from typing import Optional, List
from enum import Enum as PyEnum

# Re-define Enums for Pydantic
class UserType(str, PyEnum):
    REGISTERED = "registered"
    ANONYMOUS = "anonymous"

class UserStatus(str, PyEnum):
    BANNED = "banned"
    FLAGGED = "flagged"
    OKAY = "okay"

class ProtestImageStatus(str, PyEnum):
    APPROVED = "approved"
    FLAGGED = "flagged"
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    MISLEADING = "misleading"

class ProtestNatureType(str, PyEnum):
    CALM = "calm"
    VIOLENT = "violent"
    NOISY_BUT_NON_VIOLENT = "noisy_but_non_violent"
    THEFT_AND_BULGLARY = "theft_and_bulglary"
    AUTHORITIES_VIOLENT = "authorities_violent"



class UserBase(BaseModel):
    email: EmailStr
    password: str

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    type: UserType
    trust_level: int
    status: UserStatus
    created_at: datetime

    class Config:
        orm_mode = True

class UserSignUp(UserBase):
    type: Optional[str] = 'REGISTERED'
    trust_level: Optional[int] = 1
    status: Optional[str] = 'OKAY'
    email: EmailStr
    password: str

    class Config:
        orm_mode = True



class ProtestBase(BaseModel):
    longitude: float
    latitude: float
    title: str
    course: str
    explanation: str
    date: date
    starting_time: time
    ending_time: time
    county: str
    subcounty: str
    location_name: str

class ProtestCreate(ProtestBase):
    pass

class Protest(ProtestBase):
    id: int
    created_by: int
    created_at: datetime

    class Config:
        orm_mode = True

# --- Protest Image Schemas ---

class ProtestImageBase(BaseModel):
    image_url: str
    description: str

class ProtestImageCreate(ProtestImageBase):
    pass

class ProtestImage(ProtestImageBase):
    id: int
    protest_id: int
    submitted_by: int
    status: ProtestImageStatus
    created_at: datetime

    class Config:
        orm_mode = True

# --- Direction Mapping Schemas ---

class DirectionMappingBase(BaseModel):
    longitude: float
    latitude: float
    date: date
    time: time

class DirectionMappingCreate(DirectionMappingBase):
    pass

class DirectionMapping(DirectionMappingBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        orm_mode = True

# --- Protest Nature Schemas ---

class ProtestNatureBase(BaseModel):
    nature: ProtestNatureType
    time: time
    date: date

class ProtestNatureCreate(ProtestNatureBase):
    pass

class ProtestNature(ProtestNatureBase):
    id: int
    protest_id: int
    user_id: int
    created_at: datetime

    class Config:
        orm_mode = True


# --- Response Models ---

class PaginatedProtests(BaseModel):
    total: int
    items: List[Protest]