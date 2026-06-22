# Projects

Projects are the main workspace unit.

Each project contains:

- metadata;
- uploaded documents;
- extracted requirements;
- generated plans;
- test cases;
- traceability information;
- chat sessions;
- project members;
- resources for planning.

## Create a Project

From the projects page:

1. click create project;
2. enter a name;
3. enter a short description;
4. select an industry;
5. save.

## Industry Field

The industry field is intended to help the system understand the project domain. It should guide AI context and retrieval, but it does not replace real project documents.

Good examples:

- Energy;
- Automotive;
- Aerospace;
- Medical;
- Generic.

## Delete a Project

Project deletion is available from the project list when the frontend exposes the delete action.

Deletion should remove project-scoped records such as documents, requirements, plans, and related artifacts. For a production system, this should also include clear confirmation and audit logging.
