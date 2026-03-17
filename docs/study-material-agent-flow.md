# Study Material Agent Flow

This document explains, in simple sequence, how the study material workflow generates material for one concept.

## Purpose

The study material pipeline takes one selected concept from a subject and builds complete learning material for it in a structured order.

For each concept, the system does not generate everything in one step. It moves through multiple agents, where each agent adds one part of the final output.

## High-Level Flow

The workflow sequence in [workflow.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/graph/workflow.py) is:

1. Validate request
2. Load subject and concept data
3. Resource finder
4. Syllabus interpreter
5. Student pedagogy
6. Study material engine
7. Concept explainer
8. Formula explainer
9. Worked example generator
10. Practice and recall generator
11. Quality guardian
12. Artifact spec formatter
13. Artifact rendering
14. Zip bundle creation
15. Persist output
16. Complete or fail

## Concept-Level Sequence

### 1. Resource Finder Agent

File: [resource_finder_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/resource_finder_agent.py)

What it does:

- Finds external learning sources for the concept
- Builds the evidence pack
- Collects references, source documents, and evidence snippets

Output contributed:

- `evidence_pack`
- `references`
- `resource_required`

Why it matters:

- This is the grounding step
- Later agents use this evidence so the material is not based only on unsupported model generation

### 2. Syllabus Interpreter Agent

File: [syllabus_interpreter_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/syllabus_interpreter_agent.py)

What it does:

- Understands what the concept means inside the selected subject and grade level
- Extracts the expected coverage for that concept
- Identifies learning objectives and scope

Output contributed:

- `coverage_map`

Why it matters:

- It tells the system what should be taught for that concept
- It prevents the material from becoming too broad or off-topic

### 3. Student Pedagogy Agent

File: [student_pedagogy_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/student_pedagogy_agent.py)

What it does:

- Converts syllabus coverage into a learner-friendly teaching approach
- Plans how the concept should be explained for the target grade
- Decides the teaching depth and instructional style

Output contributed:

- `teaching_plan`

Why it matters:

- It makes the content suitable for the student level
- It helps later agents explain the concept in the right tone and difficulty

### 4. Study Material Engine Agent

File: [study_material_engine_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/study_material_engine_agent.py)

What it does:

- Generates the first full concept explanation
- Produces the main study material body
- Produces quick revision content
- Adds candidate examples and formulas

Output contributed:

- `engine_output`
  - `full_study_material`
  - `quick_revision`
  - `examples`
  - `formulas`
  - `concept_analysis`

Why it matters:

- This is the broad teaching draft for the concept
- Later agents refine this draft into structured learning components

### 5. Concept Explainer Agent

File: [concept_explainer_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/concept_explainer_agent.py)

What it does:

- Creates the core learning notes for the concept
- Writes the definition
- Writes the intuition
- Decides whether a stepwise breakdown is really needed
- Adds common mistakes and recap points

Output contributed:

- `core_notes`
  - `definition`
  - `intuition`
  - `formulas`
  - `stepwise_breakdown_required`
  - `key_steps`
  - `common_mistakes`
  - `recap`
  - `practical_examples_required`

Why it matters:

- This is the main structured concept summary
- It controls whether the final material should show a `Key Steps` section or skip it

### 6. Formula Explainer Agent

File: [formula_explainer_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/formula_explainer_agent.py)

What it does:

- Takes formulas from the core notes
- Explains each formula in a student-friendly way
- Adds variable meaning and supporting explanation

Output contributed:

- `formula_cards`

Why it matters:

- It improves formula-based topics
- It makes formulas more useful than showing raw equations only

### 7. Worked Example Agent

File: [worked_example_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/worked_example_agent.py)

What it does:

- Creates worked examples for the concept
- Uses formulas, steps, and concept meaning
- Produces examples only when they are educationally useful

Output contributed:

- `examples_pack`
  - `examples`

Why it matters:

- Examples help students move from theory to application
- This is especially important for procedural and numerical topics

### 8. Practice Recall Agent

File: [practice_recall_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/practice_recall_agent.py)

What it does:

- Creates MCQs
- Creates flashcards
- Uses the concept summary, formulas, mistakes, recap, and examples

Output contributed:

- `practice_pack`
  - `mcqs`
  - `flashcards`

Why it matters:

- It converts study material into active recall practice
- It supports topic assessment and revision

### 9. Quality Guardian Agent

File: [quality_guardian_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/quality_guardian_agent.py)

What it does:

- Reviews the generated concept material
- Checks clarity, completeness, grounding, examples, flashcards, and references
- Decides whether the concept output is acceptable
- Can trigger revision cycles if the quality is not good enough

Output contributed:

- `quality_report`
- `blocking_issues`
- `guidance`
- `revision_feedback`

Why it matters:

- This is the quality gate of the workflow
- It helps keep the output production-ready instead of accepting weak drafts

### 10. Artifact Spec Agent

File: [artifact_spec_agent.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/artifact_spec_agent.py)

What it does:

- Combines outputs from all previous agents
- Converts them into one final structured concept payload
- Preserves only the fields required for rendering and storage

Output contributed:

- `ConceptContentPack`

Main fields inside the final pack:

- definition
- intuition
- formulas
- stepwise_breakdown_required
- key_steps
- common_mistakes
- examples
- mcqs
- flashcards
- references
- recap

Why it matters:

- This is the final concept contract used by renderers and persistence
- It is the clean handoff from generation logic to output generation

## After the Agents

The agent work ends after the final `ConceptContentPack` is prepared. Then the workflow performs output and storage steps.

### 11. Learning Content Builder

File: [learning_content_service.py](/home/larwin/projects/studyguru/Backend/src/core/services/learning_content_service.py)

What it does:

- Converts `ConceptContentPack` into structured learning sections
- Builds sections like:
  - Overview
  - Key Highlights
  - Key Steps, only if really needed
  - Detailed Explanation
  - Practical Examples
  - Formulas
  - Common Mistakes
  - Summary
  - Quick Revision

Why it matters:

- This is what the frontend learning page reads and renders

### 12. Renderers

Files:

- [pdf_renderer.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/renderers/pdf_renderer.py)
- [json_renderer.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/renderers/json_renderer.py)
- [study_material_json_renderer.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/renderers/study_material_json_renderer.py)

What they do:

- Generate export files for the concept and subject
- Create output used by admin review and student access

Artifacts produced:

- PDF
- Quick revision PDF
- Quiz JSON
- Flashcards JSON
- Resources JSON
- Study material JSON

### 13. Persistence

The workflow then:

- stores artifacts
- stores the generated learning content
- stores assessment questions built from MCQs
- updates concept material version and status

## Simple End-to-End Summary

For one concept, the system follows this simple pattern:

1. Gather evidence
2. Understand syllabus scope
3. Plan the teaching style
4. Generate the main content draft
5. Extract clean concept notes
6. Explain formulas
7. Build examples
8. Build MCQs and flashcards
9. Review quality
10. Assemble final concept pack
11. Render files and save output

## Practical Example

If the concept is `Chemical Reactions and Equations`, the workflow should behave like this:

1. Resource finder gathers grounded chemistry references
2. Syllabus interpreter identifies expected grade-10 coverage
3. Student pedagogy decides how deeply to teach the topic
4. Study material engine drafts the broad explanation
5. Concept explainer creates the final definition, intuition, recap, and decides whether the topic truly needs `Key Steps`
6. Formula explainer handles symbolic equations and balancing logic if relevant
7. Worked example agent creates reaction-based examples
8. Practice recall agent creates MCQs and flashcards
9. Quality guardian checks the final concept quality
10. Artifact spec agent packages everything for rendering and saving

## Main Files To Know

- Workflow orchestrator: [workflow.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/graph/workflow.py)
- Agent registry: [agent_registry.py](/home/larwin/projects/studyguru/Backend/src/control/study_material_generation/agents/agent_registry.py)
- Final content builder: [learning_content_service.py](/home/larwin/projects/studyguru/Backend/src/core/services/learning_content_service.py)

This is the core sequence used to generate professional concept-level study material in the current backend.
