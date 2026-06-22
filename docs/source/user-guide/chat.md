# Chat

The chat feature is intended to behave like a project copilot.

## Expected Context

The chat should be able to use:

- current project metadata;
- uploaded documents;
- extracted requirements;
- generated plans;
- test cases;
- coverage status;
- relevant general knowledge.

## Useful Questions

Before generation:

```text
Which requirements are related to duplicate telemetry prevention?
```

After generation:

```text
Which requirements are covered by the latest generated plan?
```

For review:

```text
What are the highest-risk areas in this project?
```

For improvement:

```text
Suggest three additional tests for uncovered requirements.
```

## Chat Sessions

The backend has support for chat persistence and session-oriented context. The frontend should expose old chats and new chat creation clearly so the user can return to previous analysis.
