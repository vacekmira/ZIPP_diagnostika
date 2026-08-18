from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ActorOperation(BaseModel):
    technician_name: str = Field(min_length=1, max_length=100)
    expected_version: int | None = Field(default=None, ge=1)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    bay_count: int = Field(ge=1, le=100)
    default_truss_count: int = Field(ge=1, le=500)
    note: str | None = Field(default=None, max_length=4000)
    technician_name: str = Field(min_length=1, max_length=100)


class BayUpdate(ActorOperation):
    name: str = Field(min_length=1, max_length=160)


class BayResize(ActorOperation):
    truss_count: int = Field(ge=1, le=500)
    confirm: bool = False


class DiagnosticSet(ActorOperation):
    done: bool


class LabelSet(ActorOperation):
    label: str = Field(min_length=1, max_length=80)


class BulkLabelItem(BaseModel):
    truss_id: int
    label: str = Field(min_length=1, max_length=80)
    expected_version: int = Field(ge=1)


class BulkLabelSet(BaseModel):
    technician_name: str = Field(min_length=1, max_length=100)
    items: list[BulkLabelItem] = Field(min_length=1, max_length=500)


class TypeSet(ActorOperation):
    type: Literal["normal", "gable"]


class ExcludeSet(ActorOperation):
    reason: Literal["leak", "crack", "other"]
    note: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_other_note(self):
        if self.reason == "other" and not (self.note or "").strip():
            raise ValueError("Pro důvod Jiné je poznámka povinná.")
        return self


class DilationPairCreate(BaseModel):
    technician_name: str = Field(min_length=1, max_length=100)
    truss_a_id: int
    truss_b_id: int
    expected_version_a: int = Field(ge=1)
    expected_version_b: int = Field(ge=1)


class DilationPairRemove(BaseModel):
    technician_name: str = Field(min_length=1, max_length=100)
    type_a: Literal["normal", "gable"] = "normal"
    type_b: Literal["normal", "gable"] = "normal"
    expected_version_a: int = Field(ge=1)
    expected_version_b: int = Field(ge=1)
