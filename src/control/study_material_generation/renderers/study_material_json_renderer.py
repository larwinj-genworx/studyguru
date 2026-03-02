from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StudyMaterialJsonRenderer:
    def render(
        self,
        *,
        output_dir: Path,
        subject_name: str,
        grade_level: str,
        concept_payloads: list[dict[str, Any]],
    ) -> Path:
        payload = {
            "subject": subject_name,
            "grade_level": grade_level,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "concepts": concept_payloads,
        }
        output_path = output_dir / "study_material.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

    def render_concept(self, *, output_dir: Path, payload: dict[str, Any]) -> Path:
        output_path = output_dir / "study_material.json"
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path
