from __future__ import annotations

from typing import Dict, Optional, Union

from pydantic import BaseModel, ConfigDict


class NormalizedIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    firstName: Optional[str] = None
    lastName: Optional[str] = None
    initial: Optional[str] = None
    sin: Optional[str] = None
    address: Optional[str] = None
    employer: Optional[str] = None
    payrollAccount: Optional[str] = None


class NormalizedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    identity: NormalizedIdentity
    boxes: Dict[str, Union[float, str]]
    otherInfo: Dict[str, float]


class ExtractedPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: str
    boxes: Dict[str, Union[float, str]]
    otherInfo: Dict[str, float]


class MapResult(BaseModel):
    byLine: Dict[str, float]
    byField: Dict[str, Union[float, str]]


class FillInput(BaseModel):
    byField: Dict[str, Union[float, int, str]]
