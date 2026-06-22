# Product Overview

AI Test Plan Generator is a semester project and prototype of an AI-assisted test engineering platform.

The goal is not to replace a QA engineer. The goal is to reduce the time needed to read long technical documents, identify requirements, draft a test strategy, create test cases, and verify coverage.

## Core Problem

Technical validation projects usually start with many documents:

- specifications;
- architecture notes;
- safety or security constraints;
- incident reports;
- change logs;
- validation strategies;
- standards or internal testing guides.

Manually turning those documents into a complete test plan is slow and error-prone. The main difficulty is not only writing tests. The harder part is keeping evidence:

- which requirement comes from which document;
- which tests cover which requirements;
- which requirements are uncovered;
- which risks should be tested first;
- which assumptions were made during test generation.

## Product Vision

The platform provides a workflow where a user can:

1. create a project;
2. upload technical documents;
3. let the AI pipeline analyze and extract requirements;
4. generate a structured test plan;
5. inspect coverage and traceability;
6. ask a contextual chatbot questions about the project;
7. export results for presentation or review.

## Intended Users

The main users are:

- QA engineers;
- validation and verification engineers;
- system engineers;
- project managers preparing validation plans;
- AI engineering students demonstrating applied multi-agent systems.

## Current Implementation Scope

The current project includes:

- a FastAPI backend;
- a React frontend;
- authentication and basic user management;
- project and document management;
- document ingestion and chunking;
- AI generation pipeline;
- general and project-specific knowledge concepts;
- contextual chat support;
- coverage and traceability views;
- PDF export;
- Docker and Helm deployment assets;
- observability hooks.

It is best understood as a working prototype moving toward an MVP, not as a finished regulated-industry product.
