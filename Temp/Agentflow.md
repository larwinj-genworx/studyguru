# StudyGuru Agentic Flow (Admin -> Student)

## Goal
Generate high-quality, easy-to-learn study material per concept using LangGraph + specialized agents, then publish only after admin approval.

## Step-by-Step Flow

### Step-1: Admin creates Subject
- Action: Admin creates a subject (example: `8th Grade Maths`).
- System output: Subject record is created.
- Agent role: No content agent runs here.

### Step-2: Admin loads Topics/Concepts
- Action: Admin adds concepts (example: `Linear Equations`, `Percentages`).
- System output: Concept list is stored under that subject.
- Agent role: No content agent runs here.

### Step-3: Admin starts material generation job
- Action: Admin calls generate endpoint with selected concept IDs.
- System output: Job is created with status `queued -> running`.
- Agent role: Workflow initialization only.

### Step-4: Request validation node
- Node: `validate_request_node`
- Work: Validates subject and concept IDs, prepares job state.
- Agent role: No content agent; validation stage.

### Step-5: Concept load node
- Node: `load_subject_and_concepts_node`
- Work: Loads selected concepts and builds per-concept state for pipeline.
- Agent role: No content agent; context setup stage.

### Step-6: Syllabus Interpreter Agent
- Node: `syllabus_interpreter_node`
- Agent: `SyllabusInterpreterAgent`
- Role: Converts each concept into:
  - learning objectives
  - prerequisites
  - common misconceptions

### Step-7: Student Pedagogy Agent
- Node: `student_pedagogy_node`
- Agent: `StudentPedagogyAgent`
- Role: Designs student-friendly lesson flow:
  - how to teach in simple sequence
  - engagement tips
  - low-friction understanding path

### Step-8: Concept Explainer Agent
- Node: `concept_explainer_node`
- Agent: `ConceptExplainerAgent`
- Role: Creates core explanation pack:
  - definition
  - intuition
  - key steps
  - common mistakes
  - recap

### Step-9: Worked Example Agent
- Node: `worked_example_node`
- Agent: `WorkedExampleAgent`
- Role: Generates solved examples (easy -> medium) for practical understanding.

### Step-10: Practice & Recall Agent
- Node: `practice_recall_node`
- Agent: `PracticeRecallAgent`
- Role: Builds reinforcement content:
  - MCQs
  - flashcards

### Step-11: Resource Finder Agent
- Node: `resource_finder_node`
- Agent: `ResourceFinderAgent`
- Role: Collects free resources:
  - validates reachable links
  - provides fallback references if search fails

### Step-12: Quality Guardian Agent
- Node: `quality_guardian_node`
- Agent: `QualityGuardianAgent`
- Role: Quality gate checks:
  - easy language
  - content completeness
  - minimum examples/MCQs/flashcards/resources
- If not good: sends revision feedback and loops back for improvement.

### Step-13: Artifact Spec Agent
- Node: `artifact_spec_node`
- Agent: `ArtifactSpecAgent`
- Role: Converts approved content into final structured schema for renderers.

### Step-14: Artifact rendering
- Node: `artifact_render_node`
- Work: Generates files:
  - PPTX
  - DOCX
  - PDF
  - quiz JSON
  - flashcards JSON
  - resources JSON
  - ZIP bundle
- Also generates concept-level artifact bundles.

### Step-15: Persist output
- Node: `persist_job_output_node`
- Work: Saves artifact paths into job record and marks concept outputs ready for review.

### Step-16: Job completion
- Node: `complete_or_fail_node`
- Work: Marks job `completed` or `failed` with progress/errors.

### Step-17: Admin review
- Action: Admin downloads and checks generated materials.
- Agent role: No generation agent; human review stage.

### Step-18: Admin regenerate (optional)
- Action: If not satisfied, admin calls regenerate with revision note.
- Work: New job runs same pipeline with feedback-guided refinement.

### Step-19: Admin approve
- Action: Admin approves generated concept materials.
- Work: Material lifecycle moves to `approved`.

### Step-20: Admin publish subject
- Action: Admin publishes subject.
- Rule: Publish is allowed only when required concept materials are approved.
- Work: Lifecycle moves to `published`.

### Step-21: Student consumption
- Action: Student selects published subject and concepts.
- Work: Student can view/download only published concept materials.
- Agent role: No generation agent on student side (read-only consumption).

## Final Outcome
- Admin controls quality through review/regeneration/approval.
- Student gets clean, understandable, concept-wise material.
- Workflow is production-oriented: validated, staged, quality-gated, and publish-controlled.
