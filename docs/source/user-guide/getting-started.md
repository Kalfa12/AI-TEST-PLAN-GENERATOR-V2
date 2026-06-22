# Getting Started

## Sign In

Open the frontend and sign in with a test account.

For a local seeded demo, the usual test account is:

- Email: `admin@example.com`
- Password: `password123`

If the account does not exist, create it using the backend admin script:

```bash
python scripts/create_admin.py
```

## Basic Workflow

The normal user workflow is:

1. create a project;
2. upload project documents;
3. wait for document ingestion;
4. inspect extracted requirements;
5. generate a test plan;
6. review test cases and traceability;
7. ask the chatbot contextual questions;
8. export the plan.

## Recommended Sample Documents

For a first test of the application, use the sample project documents in:

```text
docs/live-demo-project-docs/pdf/
```

Those files were created for this application and are compatible with the general testing knowledge base.
