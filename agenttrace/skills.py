from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from pydantic import BaseModel, Field


class SkillParameter(BaseModel):
    name: str
    type: str = "string"
    required: bool = True
    description: str | None = None


class SkillDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    parameters: list[SkillParameter] = Field(default_factory=list)
    body_path: str | None = None

    @classmethod
    def from_markdown_skill(cls, path: str | Path) -> SkillDefinition:
        """Parse minimal SKILL.md-style frontmatter (name + description)."""
        text = Path(path).read_text(encoding="utf-8")
        name = Path(path).parent.name
        description = ""
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip('"')
        return cls(
            name=name,
            description=description or f"Skill loaded from {path}",
            body_path=str(path),
        )


class SkillDebugResult(BaseModel):
    skill: str
    valid_input: bool
    valid_output: bool
    input_errors: list[str] = Field(default_factory=list)
    output_errors: list[str] = Field(default_factory=list)
    param_issues: list[str] = Field(default_factory=list)


def validate_against_schema(data: Any, schema: dict[str, Any]) -> list[str]:
    if not schema:
        return []
    validator = Draft202012Validator(schema)
    errors = []
    for err in sorted(validator.iter_errors(data), key=lambda e: e.path):
        errors.append(err.message)
    return errors


def debug_skill_io(
    skill: SkillDefinition,
    input_data: Any,
    output_data: Any | None = None,
) -> SkillDebugResult:
    input_errors = validate_against_schema(input_data, skill.input_schema)
    output_errors = validate_against_schema(output_data, skill.output_schema) if output_data is not None else []

    param_issues: list[str] = []
    if isinstance(input_data, dict):
        for p in skill.parameters:
            if p.required and p.name not in input_data:
                param_issues.append(f"Missing required parameter: {p.name}")
            if p.name in input_data and p.type == "integer":
                val = input_data[p.name]
                if not isinstance(val, int):
                    param_issues.append(f"Parameter {p.name} should be integer, got {type(val).__name__}")

    return SkillDebugResult(
        skill=skill.name,
        valid_input=len(input_errors) == 0 and len(param_issues) == 0,
        valid_output=len(output_errors) == 0,
        input_errors=input_errors,
        output_errors=output_errors,
        param_issues=param_issues,
    )


def run_skill_standalone(
    skill: SkillDefinition,
    input_data: dict[str, Any],
    executor: Any | None = None,
) -> dict[str, Any]:
    """Dry-run / mock execute with validation only when no executor."""
    debug = debug_skill_io(skill, input_data)
    if not debug.valid_input:
        return {"ok": False, "debug": debug.model_dump(), "output": None}
    if executor is None:
        return {"ok": True, "debug": debug.model_dump(), "output": {"echo": input_data}}
    output = executor(input_data)
    debug_out = debug_skill_io(skill, input_data, output)
    return {"ok": debug_out.valid_output, "debug": debug_out.model_dump(), "output": output}