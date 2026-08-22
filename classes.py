from pydantic import BaseModel, Field
from datetime import datetime, time

# ==========================================
# CLASSES
# ==========================================

# Classes added to accept participant information and edits, which can be passed as one piece of information into our functions.
class ParticipantCreate(BaseModel):
    username: str
    name: str
    bio: str | None = None
    timezone: str
    is_hidden: bool = False

class ParticipantEdit(BaseModel):
    username: str | None = None
    name: str | None = None
    bio: str | None = None
    timezone: str | None = None
    is_hidden: bool | None = None


# Group Classes
class GroupCreate(BaseModel):
    name: str
    description: str
    invite_only: bool = False
    is_hidden: bool = False
    members_can_invite: bool = False

class GroupEdit(BaseModel):
    name: str | None = None
    description: str | None = None
    invite_only: bool | None = None
    is_hidden: bool | None = None
    members_can_invite: bool | None = None


# Member Classes
# class MemberCreate(BaseModel):
#     name: str
#     description: str
#     invite_only: bool = False
#     is_hidden: bool = False
#     members_can_invite: bool = False

# class MemberEdit(BaseModel):
#     name: str
#     description: str
#     invite_only: bool = False
#     is_hidden: bool = False
#     members_can_invite: bool = False


# Availability Classes
class RecurringAvailabilityCreate(BaseModel):
    group_ids: list[int] | None = None
    weekday: int = Field(ge=0, le=6)
    start_time: time
    end_time: time
    end_day_offset: int = Field(default=0, ge=0, le=6)
    is_available: int = Field(ge=0, le=2)
    description: str | None = None


class RecurringAvailabilityEdit(BaseModel):
    group_id: int | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    end_day_offset: int | None = Field(default=None, ge=0, le=6)
    is_available: int | None = Field(default=None, ge=0, le=2)
    description: str | None = None


class SpecificAvailabilityCreate(BaseModel):
    group_ids: list[int] | None = None
    start_datetime: datetime
    end_datetime: datetime
    is_available: int = Field(ge=0, le=2)
    description: str | None = None


class SpecificAvailabilityEdit(BaseModel):
    group_id: int | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    is_available: int | None = Field(default=None, ge=0, le=2)
    description: str | None = None


# Event Classes
class EventCreate(BaseModel):
    name: str | None = None
    description: str | None = None
    timezone: str


class EventEdit(BaseModel):
    name: str | None = None
    description: str | None = None
    timezone: str | None = None


class RecurringEventTimeCreate(BaseModel):
    weekday: int
    start_time: time
    end_time: time
    end_day_offset: int = Field(default=0, ge=0, le=6)


class RecurringEventTimeEdit(BaseModel):
    weekday: int | None = Field(default=None, ge=0, le=6)
    start_time: time | None = None
    end_time: time | None = None
    end_day_offset: int | None = Field(default=None, ge=0, le=6)
    

class SpecificEventTimeCreate(BaseModel):
    start_datetime: datetime
    end_datetime: datetime


class SpecificEventTimeEdit(BaseModel):
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None




# Ban Classes
class BanCreate(BaseModel):
    reason_for_ban: str | None = None

class BanEdit(BaseModel):
    reason: str
    is_unban_reason: bool = False
    # if false, "is_ban_reason"

class BanRemove(BaseModel):
    reason_for_unban: str | None = None



