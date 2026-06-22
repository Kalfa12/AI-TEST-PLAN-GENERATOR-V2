# AI Brain

The AI brain is the core product differentiator.

It combines document retrieval, multiple specialized agents, structured outputs, traceability, and human review.

## Agent Pipeline

```{mermaid}
flowchart TD
    Start["Start"] --> Analyst["Document Analyst"]
    Analyst --> Extractor["Requirement Extractor"]
    Extractor --> ReqReview["Requirement Reviewer"]
    ReqReview --> Architect["Test Architect"]
    Architect --> Generator["Test Generator"]
    Generator --> Trace["Traceability Agent"]
    Trace --> Reviewer["Plan Reviewer"]
    Reviewer --> Defects["Defect Aggregator"]
    Defects --> Planner["Planner"]
    Planner --> End["Generated Plan"]
```

## Agent Responsibilities

| Agent | Role |
| --- | --- |
| Document Analyst | Summarizes the corpus and identifies gaps |
| Requirement Extractor | Converts document content into structured requirements |
| Requirement Reviewer | Reviews requirement quality |
| Test Architect | Creates the plan shell and strategy |
| Test Generator | Creates test cases and instructions |
| Traceability Agent | Links requirements to tests and coverage |
| Plan Reviewer | Reviews the complete generated plan |
| Defect Aggregator | Deduplicates and organizes detected issues |
| Planner | Produces planning and execution sequencing |

## LLM Provider Abstraction

The project uses a provider-neutral gateway. Agents request a model tier:

- `fast`;
- `balanced`;
- `smart`;
- `embedding`.

The actual provider and model are selected by environment variables.

Example:

```bash
LLM_MODEL_SMART=deepseek/deepseek-chat
LLM_MODEL_BALANCED=deepseek/deepseek-chat
LLM_MODEL_FAST=deepseek/deepseek-chat
LLM_MODEL_EMBEDDING=nvidia/nv-embed-v1
```

## Retrieval Context

The intended retrieval context includes:

- project document chunks;
- extracted requirements;
- generated plans and test cases;
- coverage information;
- general knowledge base chunks;
- chat history.

## Why Multi-Agent?

The problem is easier to control when split into specialized tasks.

One agent extracting requirements should not also decide the validation strategy. One deterministic traceability step should not be replaced by free-form text generation.

This separation makes outputs easier to inspect and debug.
