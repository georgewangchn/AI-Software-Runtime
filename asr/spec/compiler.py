from __future__ import annotations

import json
import re
from pathlib import Path

from asr.agents.llm_tracker import log_token_usage
from asr.agents.opencode_backend import opencode_completion
from asr.config.models import ModelConfig
from asr.spec.models import Specification


class SpecCompiler:
    def __init__(self, model_config: ModelConfig):
        self._model_config = model_config

    async def compile(
        self,
        natural_language: str,
        constraints: list[dict] | None = None,
    ) -> Specification:
        messages = self._build_prompt(natural_language, constraints)

        for attempt in range(3):
            try:
                user = messages[-1]["content"] if messages else ""
                system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
                prompt = f"{system}\n\n{user}" if system else user
                text, pt, ct, tt = await opencode_completion(prompt, Path("/tmp"))
                log_token_usage("spec_compiler", "opencode/qwen3-next-80b", {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt})
                spec_dict = self._extract_yaml(text)
                spec = Specification(**spec_dict)
                result = spec.validate_spec()
                if result.valid:
                    return spec
                if attempt < 2:
                    messages.append({"role": "assistant", "content": text})
                    messages.append(
                        {
                            "role": "user",
                            "content": f"Validation errors: {result.errors}. Please fix and output valid YAML.",
                        }
                    )
            except Exception as e:
                if attempt >= 2:
                    raise RuntimeError(f"Spec compilation failed after 3 attempts: {e}")
                continue

        raise RuntimeError("Spec compilation failed: unable to produce valid spec")

    async def compile_from_file(self, yaml_path: str) -> Specification:
        import yaml

        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        return Specification(**data)

    def _build_prompt(
        self,
        nl: str,
        constraints: list[dict] | None = None,
    ) -> list[dict]:
        system_prompt = (
            "Output ONLY valid YAML. No explanations, no file reading, no thinking. "
            "Schema:\n"
            "goal: <string>\n"
            "constraints:\n"
            "  - name: <string>\n"
            "    description: <string>\n"
            "    type: must|should|must_not\n"
            "acceptance:\n"
            "  - name: <string>\n"
            "    description: <string>\n"
            "    expected_behavior: <string>\n"
            "features:\n"
            "  - name: <string>\n"
            "    description: <string>\n"
            "Do NOT use markdown fences. raw YAML only."
        )

        user_prompt = f"Requirements:\n{nl}"
        if constraints:
            user_prompt += f"\n\nAdditional constraints:\n{json.dumps(constraints, indent=2)}"

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _extract_yaml(self, text: str) -> dict:
        import yaml

        cleaned = re.sub(r"```(?:yaml)?\s*", "", text)
        cleaned = re.sub(r"```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return yaml.safe_load(cleaned)
        except yaml.YAMLError:
            pass

        m = re.search(r"goal\s*:", cleaned)
        if m:
            cleaned = cleaned[m.start():]
            cleaned = cleaned.strip()

        return yaml.safe_load(cleaned)
