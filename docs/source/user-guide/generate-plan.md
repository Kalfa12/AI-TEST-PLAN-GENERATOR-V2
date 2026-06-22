# Generate a Plan

Plan generation is the central workflow of the application.

## Inputs

The generator uses:

- project metadata;
- uploaded document chunks;
- extracted requirements;
- general knowledge base context;
- user goal;
- previous generated artifacts when available.

## Goal Field

The goal field helps steer the generation.

It is not strictly necessary to say "generate a test plan", because that is already the product purpose. However, the goal is useful when it adds priorities.

Good goal:

```text
Generate a risk-based validation plan. Prioritize cybersecurity, local buffering, duplicate prevention, device health timing, and traceability.
```

Weak goal:

```text
test plan
```

## Autonomous Mode

Autonomous mode runs the pipeline without stopping for review. It is better for fast demos.

## Interactive Mode

Interactive mode pauses at selected stages so the user can review and guide the agents.

Use interactive mode when you want to demonstrate human-in-the-loop AI.

Use autonomous mode when time is limited.
