# Product Features

## Project Workspace

Each project groups documents, requirements, test plans, chat context, project members, and planning resources.

Typical project fields:

- project name;
- description;
- industry;
- documents;
- requirements;
- generated plans;
- project resources;
- members.

## Document Upload

The platform supports technical document upload and ingestion.

Supported source types in the backend include:

- PDF;
- DOCX;
- Markdown;
- plain text-like technical content depending on loader support.

Uploaded documents are extracted, chunked, stored, and made available to the AI pipeline.

## Requirement Extraction

The AI pipeline identifies normative requirements and converts them into structured requirement objects.

Requirements can then be used for:

- test planning;
- traceability;
- coverage analysis;
- chatbot answers.

## Test Plan Generation

The plan generation flow produces:

- a test plan shell;
- test objectives;
- test strategy;
- scope and out-of-scope elements;
- risks;
- test cases;
- traceability links;
- coverage information;
- planning recommendations.

The generation can be autonomous or interactive depending on the selected mode.

## Human-in-the-Loop Review

Interactive mode pauses generation at review checkpoints. The user can inspect an agent output, accept it, or provide feedback before the next step.

This is important because industrial validation work requires human review.

## Knowledge Base

The application separates two types of knowledge:

- general knowledge, such as testing methodology, cybersecurity checklists, traceability guidance, and domain patterns;
- project knowledge, such as uploaded project requirements, architecture notes, incidents, and generated artifacts.

The intended behavior is that reusable knowledge guides the method, while project knowledge grounds the generated plan.

## Contextual Chat

The chatbot is intended to answer questions using project context:

- current project metadata;
- uploaded documents;
- extracted requirements;
- latest generated plans and test cases;
- coverage information;
- relevant general knowledge.

## Traceability and Coverage

Traceability links connect:

- document chunks to requirements;
- requirements to test cases;
- requirements to generated plans;
- coverage status to gaps.

Coverage views help users see what is tested and what is still missing.

## Exports

The frontend includes PDF export support for generated plans and test cases. The exported file is useful for project presentation, review, and demonstration.
