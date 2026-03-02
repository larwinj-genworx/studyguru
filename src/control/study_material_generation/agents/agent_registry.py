from __future__ import annotations

from dataclasses import dataclass

from src.config.settings import Settings
from .artifact_spec_agent import ArtifactSpecAgent
from .concept_explainer_agent import ConceptExplainerAgent
from .practice_recall_agent import PracticeRecallAgent
from .quality_guardian_agent import QualityGuardianAgent
from .resource_finder_agent import ResourceFinderAgent
from .study_material_engine_agent import StudyMaterialEngineAgent
from .formula_explainer_agent import FormulaExplainerAgent
from .student_pedagogy_agent import StudentPedagogyAgent
from .syllabus_interpreter_agent import SyllabusInterpreterAgent
from .worked_example_agent import WorkedExampleAgent


@dataclass
class AgentRegistry:
    syllabus_interpreter: SyllabusInterpreterAgent
    student_pedagogy: StudentPedagogyAgent
    study_material_engine: StudyMaterialEngineAgent
    formula_explainer: FormulaExplainerAgent
    concept_explainer: ConceptExplainerAgent
    worked_example: WorkedExampleAgent
    practice_recall: PracticeRecallAgent
    resource_finder: ResourceFinderAgent
    quality_guardian: QualityGuardianAgent
    artifact_spec: ArtifactSpecAgent


def build_agent_registry(settings: Settings) -> AgentRegistry:
    return AgentRegistry(
        syllabus_interpreter=SyllabusInterpreterAgent(settings),
        student_pedagogy=StudentPedagogyAgent(settings),
        study_material_engine=StudyMaterialEngineAgent(settings),
        formula_explainer=FormulaExplainerAgent(settings),
        concept_explainer=ConceptExplainerAgent(settings),
        worked_example=WorkedExampleAgent(settings),
        practice_recall=PracticeRecallAgent(settings),
        resource_finder=ResourceFinderAgent(settings),
        quality_guardian=QualityGuardianAgent(settings),
        artifact_spec=ArtifactSpecAgent(settings),
    )
