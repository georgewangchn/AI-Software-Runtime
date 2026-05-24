from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Constraint(BaseModel):
    name: str
    description: str = ""
    type: str = "must"


class AcceptanceCriteria(BaseModel):
    name: str
    description: str = ""
    expected_behavior: str = ""


class Feature(BaseModel):
    name: str
    description: str = ""


class ValidationResult(BaseModel):
    valid: bool = True
    errors: list[str] = Field(default_factory=list)


class Specification(BaseModel):
    goal: str = ""
    constraints: list[Constraint] = Field(default_factory=list)
    acceptance: list[AcceptanceCriteria] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)

    def validate_spec(self) -> ValidationResult:
        errors = []
        if not self.goal:
            errors.append("goal is required")
        return ValidationResult(valid=len(errors) == 0, errors=errors)
