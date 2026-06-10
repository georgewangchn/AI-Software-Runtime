"""Tests for ASR specification models."""

import pytest
from pydantic import ValidationError

from asr.spec.models import Constraint, AcceptanceCriteria, Feature, ValidationResult, Specification


def test_constraint_defaults():
    """Test Constraint with default values."""
    constraint = Constraint(name="max_response_time")
    assert constraint.name == "max_response_time"
    assert constraint.description == ""
    assert constraint.type == "must"


def test_constraint_all_fields():
    """Test Constraint with all fields populated."""
    constraint = Constraint(
        name="max_response_time",
        description="API response time must be under 200ms",
        type="should"
    )
    assert constraint.name == "max_response_time"
    assert constraint.description == "API response time must be under 200ms"
    assert constraint.type == "should"


def test_acceptance_criteria_defaults():
    """Test AcceptanceCriteria with default values."""
    criteria = AcceptanceCriteria(name="user_authentication")
    assert criteria.name == "user_authentication"
    assert criteria.description == ""
    assert criteria.expected_behavior == ""


def test_acceptance_criteria_all_fields():
    """Test AcceptanceCriteria with all fields populated."""
    criteria = AcceptanceCriteria(
        name="user_authentication",
        description="Users must authenticate before accessing resources",
        expected_behavior="System prompts for username and password"
    )
    assert criteria.name == "user_authentication"
    assert criteria.description == "Users must authenticate before accessing resources"
    assert criteria.expected_behavior == "System prompts for username and password"


def test_feature_defaults():
    """Test Feature with default values."""
    feature = Feature(name="user_login")
    assert feature.name == "user_login"
    assert feature.description == ""


def test_feature_with_description():
    """Test Feature with description."""
    feature = Feature(
        name="user_login",
        description="Allow users to login with username and password"
    )
    assert feature.name == "user_login"
    assert feature.description == "Allow users to login with username and password"


def test_validation_result_defaults():
    """Test ValidationResult with default values."""
    result = ValidationResult()
    assert result.valid is True
    assert result.errors == []


def test_validation_result_with_errors():
    """Test ValidationResult with errors."""
    result = ValidationResult(
        valid=False,
        errors=["Missing required field", "Invalid type"]
    )
    assert result.valid is False
    assert len(result.errors) == 2
    assert "Missing required field" in result.errors
    assert "Invalid type" in result.errors


def test_specification_defaults():
    """Test Specification with default values."""
    spec = Specification()
    assert spec.goal == ""
    assert spec.constraints == []
    assert spec.acceptance == []
    assert spec.features == []


def test_specification_with_goal():
    """Test Specification with goal only."""
    spec = Specification(goal="Build a REST API")
    assert spec.goal == "Build a REST API"
    assert spec.constraints == []
    assert spec.acceptance == []
    assert spec.features == []


def test_specification_all_fields():
    """Test Specification with all fields populated."""
    constraint = Constraint(name="max_response_time", description="Response under 200ms")
    criteria = AcceptanceCriteria(name="login", expected_behavior="User can login")
    feature = Feature(name="user_authentication", description="Login system")

    spec = Specification(
        goal="Build a REST API",
        constraints=[constraint],
        acceptance=[criteria],
        features=[feature]
    )

    assert spec.goal == "Build a REST API"
    assert len(spec.constraints) == 1
    assert spec.constraints[0].name == "max_response_time"
    assert len(spec.acceptance) == 1
    assert spec.acceptance[0].name == "login"
    assert len(spec.features) == 1
    assert spec.features[0].name == "user_authentication"


def test_specification_validate_spec_empty_goal():
    """Test Specification validation with empty goal."""
    spec = Specification(goal="")
    result = spec.validate_spec()
    assert result.valid is False
    assert "goal is required" in result.errors


def test_specification_validate_spec_valid():
    """Test Specification validation with valid spec."""
    spec = Specification(goal="Build a system")
    result = spec.validate_spec()
    assert result.valid is True
    assert len(result.errors) == 0


def test_specification_serialization():
    """Test Specification serialization."""
    spec = Specification(
        goal="Build a system",
        constraints=[Constraint(name="must_have")],
        features=[Feature(name="feature1")]
    )
    data = spec.model_dump()
    assert data["goal"] == "Build a system"
    assert len(data["constraints"]) == 1
    assert len(data["features"]) == 1


def test_specification_deserialization():
    """Test Specification deserialization."""
    data = {
        "goal": "Build a system",
        "constraints": [{"name": "must_have", "description": "", "type": "must"}],
        "acceptance": [],
        "features": [{"name": "feature1", "description": ""}]
    }
    spec = Specification(**data)
    assert spec.goal == "Build a system"
    assert len(spec.constraints) == 1
    assert spec.constraints[0].name == "must_have"
    assert len(spec.features) == 1
    assert spec.features[0].name == "feature1"


def test_specification_update_fields():
    """Test Specification field updates."""
    spec = Specification(goal="Initial goal")
    assert spec.goal == "Initial goal"

    spec2 = spec.model_copy(update={"goal": "Updated goal"})
    assert spec.goal == "Initial goal"
    assert spec2.goal == "Updated goal"


def test_constraint_serialization():
    """Test Constraint serialization."""
    constraint = Constraint(
        name="test_constraint",
        description="Test description",
        type="should"
    )
    data = constraint.model_dump()
    assert data["name"] == "test_constraint"
    assert data["description"] == "Test description"
    assert data["type"] == "should"


def test_acceptance_criteria_serialization():
    """Test AcceptanceCriteria serialization."""
    criteria = AcceptanceCriteria(
        name="test_criteria",
        description="Test description",
        expected_behavior="Test behavior"
    )
    data = criteria.model_dump()
    assert data["name"] == "test_criteria"
    assert data["description"] == "Test description"
    assert data["expected_behavior"] == "Test behavior"


def test_feature_serialization():
    """Test Feature serialization."""
    feature = Feature(
        name="test_feature",
        description="Test description"
    )
    data = feature.model_dump()
    assert data["name"] == "test_feature"
    assert data["description"] == "Test description"
