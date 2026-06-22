# Data Model

The application uses Python domain repositories and Pydantic models.

## Main Concepts

| Concept | Meaning |
| --- | --- |
| User | Person authenticated in the application |
| Project | Workspace for documents, requirements, plans, and chat |
| Document | Uploaded technical file |
| Chunk | Extracted document segment used for retrieval |
| Requirement | Structured requirement extracted from documents |
| Test Plan | Generated plan containing strategy and test cases |
| Test Case | Concrete validation instruction linked to requirements |
| Traceability Link | Relationship between document, requirement, and test |
| Chat Session | Conversation around a project |
| Artifact | Stored generated output or exportable result |

## Repositories

Domain repositories are located in:

```text
src/ai_testplan_generator/domain/
```

They handle persistence for projects, users, jobs, artifacts, and chat actions.

## Memory Stores

The memory layer separates:

- episodic memory for conversation and event history;
- semantic memory for vector retrieval;
- cross-document graph memory for traceability relationships.

This separation lets the system use lightweight local backends during development and stronger infrastructure in production.
