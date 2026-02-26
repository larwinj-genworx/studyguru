# StudyGuru - Current Agentic Approach

## 1) Objective
Build an admin-controlled, agentic study-material pipeline where content is generated per concept, reviewed by admin, and published only after approval. Students can access only published concept materials.

## 2) Core Flow
1. Admin creates subject.
2. Admin adds concepts/topics.
3. Admin generates study material (async job).
4. System runs LangGraph workflow with specialized agents.
5. Admin reviews output and can regenerate with feedback.
6. Admin approves selected/all concept materials.
7. Admin publishes subject.
8. Student browses published subjects/concepts and views published materials.

## 3) Agent Flow (Node-wise)
1. `SyllabusInterpreterAgent`: Defines objectives, prerequisites, misconceptions.
2. `StudentPedagogyAgent`: Builds easy, student-friendly lesson flow.
3. `ConceptExplainerAgent`: Creates definition, intuition, key steps, recap.
4. `WorkedExampleAgent`: Produces solved practical examples.
5. `PracticeRecallAgent`: Generates MCQs + flashcards.
6. `ResourceFinderAgent`: Collects free validated resources (with fallback links).
7. `QualityGuardianAgent`: Checks clarity, completeness, readability, and minimum coverage.
8. `ArtifactSpecAgent`: Finalizes renderer-ready structured output.
    -  Each Agent works in sequential manner.   

## 4) Generated Study Material (RightNow) : 
For each concept, system generates:
- PPTX
- DOCX
- PDF (quick revision)
- Quiz JSON
- Flashcards JSON
- Resources JSON
- ZIP bundle (aggregate + concept-level bundles)

## 5) Governance and Quality Controls
- Publish is blocked until materials are approved.
- Admin can regenerate until satisfied.
- Student can access only published concept artifacts.
- Workflow includes validation, revision loop, and progress/status tracking.

## 6) Short Example
Subject: `8th Grade Maths`  
Concept: `Linear Equations`

1. Admin creates subject and adds concept.
2. Admin starts generation job.
3. Agents produce explanation, examples, MCQs, flashcards, resources, and files (PPTX/DOCX/PDF/JSON).
4. Admin reviews files; if needed, regenerates with note: "simplify language and add clearer examples."
5. Admin approves concept material.
6. Admin publishes subject.
7. Student selects `Linear Equations` and studies published material directly.

## 7) Specification:
- Right now i am using the Research and High-Reasoning supporting LLM to produce the study material.
- Splitting all the operations and given each tasks to separate agent that would increase the accuracy of generating the study material.
- Also keep separate agent which validate the generated material is in proper, expected manner only..
- Using Duckduckgo search engine to get the realtime references and materials.
