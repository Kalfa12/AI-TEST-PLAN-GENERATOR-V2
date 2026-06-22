# Operational Scope

This page summarizes the practical operating conditions to consider when using the application.

## External AI Dependency

The generation pipeline depends on configured LLM providers. If the provider is slow, rate-limited, or unavailable, generation can fail or take longer than expected.

## Long Document Processing

Large documents can produce many chunks. This improves retrieval coverage but increases ingestion time, embedding cost, and database pressure.

## SQLite Concurrency

Local development uses SQLite. SQLite is convenient but can lock under concurrent writes, especially when ingestion, generation, and chat all write at the same time.

For a production deployment, use a database architecture designed for concurrent workloads.

## Interactive Runs

Interactive generation is useful for human review. For production-grade usage, persistent checkpointers are recommended for long-running interactive workflows.

## Traceability Quality

The platform builds traceability links, but the quality of those links depends on:

- document extraction quality;
- requirement extraction quality;
- model output quality;
- retrieval configuration;
- user review.

Traceability should be reviewed by a human before formal validation decisions.
