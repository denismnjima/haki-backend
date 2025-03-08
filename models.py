from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Date, Time
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy_utils import ChoiceType
from sqlalchemy.sql import func

from database import Base

PROTEST_IMAGE_STATUS_CHOICES = [
    ("approved", "Approved"),
    ("flagged", "Flagged"),
    ("verified", "Verified"),
    ("not_verified", "Not Verified"),
    ("misleading", "Misleading")
]

PROTEST_NATURE_TYPE_CHOICES = [
    ("calm", "Calm"),
    ("violent", "Violent"),
    ("noisy_but_non_violent", "Noisy but Non-Violent"),
    ("theft_and_bulglary", "Theft and Bulglary"),
    ("authorities_violent", "Authorities Violent")
]

USER_TYPE_CHOICES = [
    ("registered", "Registered"),
    ("anonymous", "Anonymous")
]

USER_STATUS_CHOICES = [
    ("banned", "Banned"),
    ("flagged", "Flagged"),
    ("okay", "Okay")
]

class Protest(Base):
    __tablename__ = "protests"

    id = Column(Integer, primary_key=True, index=True)
    longitude = Column(Float)
    latitude = Column(Float)
    title = Column(String(255))
    course = Column(String(255))
    explanation = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    starting_time = Column(Time)
    ending_time = Column(Time)
    county = Column(String(100))
    subcounty = Column(String(100))
    location_name = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", back_populates="protests")
    images = relationship("ProtestImage", back_populates="protest")
    natures = relationship("ProtestNature", back_populates="protest")


class ProtestImage(Base):
    __tablename__ = "protest_images"

    id = Column(Integer, primary_key=True, index=True)
    protest_id = Column(Integer, ForeignKey("protests.id"))
    image_url = Column(String(255))
    description = Column(Text)
    submitted_by = Column(Integer, ForeignKey("users.id"))
    status = Column(ChoiceType(PROTEST_IMAGE_STATUS_CHOICES), default="not_verified")  # Use ChoiceType
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    protest = relationship("Protest", back_populates="images")
    submitter = relationship("User", back_populates="images")


class DirectionMapping(Base):
    __tablename__ = "direction_mapping"

    id = Column(Integer, primary_key=True, index=True)
    longitude = Column(Float)
    latitude = Column(Float)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(Date)
    time = Column(Time)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="directions")


class ProtestNature(Base):
    __tablename__ = "protest_nature"

    id = Column(Integer, primary_key=True, index=True)
    protest_id = Column(Integer, ForeignKey("protests.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    nature = Column(ChoiceType(PROTEST_NATURE_TYPE_CHOICES))  # Use ChoiceType
    time = Column(Time)
    date = Column(Date)

    protest = relationship("Protest", back_populates="natures")
    user = relationship("User", back_populates="natures")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True)
    password = Column(String(255))
    type = Column(ChoiceType(USER_TYPE_CHOICES), default="registered")  # Use ChoiceType
    trust_level = Column(Integer, default=0)
    status = Column(ChoiceType(USER_STATUS_CHOICES), default="okay")  # Use ChoiceType
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    protests = relationship("Protest", back_populates="creator")
    images = relationship("ProtestImage", back_populates="submitter")
    directions = relationship("DirectionMapping", back_populates="user")
    natures = relationship("ProtestNature", back_populates="user")