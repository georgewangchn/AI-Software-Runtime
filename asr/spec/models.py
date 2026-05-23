from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Constraint(BaseModel):
    name: str
    description: str = ""
    type: Literal["must", "should", "must_not"] = "must"


class AcceptanceTest(BaseModel):
    name: str
    description: str = ""
    expected_behavior: str = ""


class Feature(BaseModel):
    name: str
    description: str = ""
    acceptance_tests: list[AcceptanceTest] = Field(default_factory=list)


class SpecValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Specification(BaseModel):
    goal: str
    constraints: list[Constraint] = Field(default_factory=list)
    acceptance: list[AcceptanceTest] = Field(default_factory=list)
    features: list[Feature] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def validate_spec(self) -> SpecValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        if not self.goal.strip():
            errors.append("goal must not be empty")

        if not self.acceptance:
            errors.append("at least one acceptance test is required")

        feature_names = [f.name for f in self.features if f.name]
        if len(feature_names) != len(set(feature_names)):
            warnings.append("duplicate feature names found")

        constraint_names = [c.name for c in self.constraints if c.name]
        if len(constraint_names) != len(set(constraint_names)):
            warnings.append("duplicate constraint names found")

        test_names = [t.name for t in self.acceptance if t.name]
        if len(test_names) != len(set(test_names)):
            warnings.append("duplicate acceptance test names found")

        return SpecValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
