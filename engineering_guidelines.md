# Engineering Guidelines
## Workspace Intelligence Engine (WIE)
Version: 1.0

---

# Purpose

This document defines the engineering principles, coding standards, architectural constraints, and development workflow for the Workspace Intelligence Engine.

This document is the engineering rulebook.

Whenever there is uncertainty, these guidelines should be followed unless the architecture specification explicitly states otherwise.

---

# Core Engineering Philosophy

The project should prioritize:

- Correctness
- Maintainability
- Readability
- Extensibility
- Testability
- Scalability

over writing clever or highly optimized code.

Readable code is preferred over clever code.

---

# General Development Rules

1. Never skip implementation phases.

2. Complete only one phase at a time.

3. Every phase must leave the application in a runnable state.

4. Never implement future features early.

5. Every feature must have a clear purpose.

6. Avoid premature optimization.

7. Architecture is more important than speed of implementation.

---

# Software Design Principles

Follow SOLID principles whenever appropriate.

Prefer:

- Composition over inheritance.
- Dependency injection over tightly coupled modules.
- Interfaces over concrete implementations where beneficial.
- Small reusable services.

Avoid:

- God classes.
- Circular dependencies.
- Deep inheritance hierarchies.
- Shared mutable state.

---

# Single Responsibility Rule

Every module should have one responsibility.

Examples

Good

Authentication Service

Only manages authentication.

Parser

Only parses files.

Retriever

Only retrieves context.

Embedding Service

Only generates embeddings.

Bad

Parser that also stores vectors.

Retriever that calls frontend APIs.

Authentication service that knows about workspaces.

---

# Layer Boundaries

Respect architectural boundaries.

Authentication

↓

Workspace

↓

Background Processing

↓

Parsing

↓

Chunking

↓

Embeddings

↓

Knowledge Layer

↓

Intent Router

↓

Retrieval

↓

LLM Gateway

↓

Actions

↓

API

↓

Frontend

Lower layers should never depend on higher layers.

---

# LLM Philosophy

The LLM is not the application.

The LLM is one service.

Always prefer deterministic code.

Examples

Good

Metadata search

File listing

Sorting

Filtering

Statistics

Workspace management

These should never require an LLM.

Use the LLM only for

- reasoning
- summarization
- explanation
- generation

LLM should always be the final step.

---

# Intent First

Every user request must pass through the Intent Router.

Never send raw user prompts directly to the LLM.

Determine

- intent
- required services
- execution plan

before generation.

---

# Modularity

Every service should be independently replaceable.

Examples

Replace

OpenAI

↓

Gemini

without changing business logic.

Replace

Qdrant

↓

pgvector

without affecting frontend.

Replace

PaddleOCR

↓

Tesseract

without changing parsing pipeline.

---

# Coding Standards

Use

- meaningful names
- small functions
- descriptive variable names
- explicit return types
- type hints

Avoid

single-letter variables

deep nesting

magic numbers

duplicated code

---

# Function Size

Aim for

20–40 lines

Maximum

60 lines

If longer,

consider extracting helper functions.

---

# Class Design

Classes should represent one concept.

Examples

WorkspaceParser

EmbeddingService

MetadataService

IntentRouter

LLMGateway

Avoid

Utility classes containing unrelated methods.

---

# Error Handling

Never ignore exceptions.

Every exception should

- be logged
- contain meaningful information
- return useful errors

Never expose internal stack traces to users.

---

# Logging

Log important events.

Examples

Workspace uploaded

Job started

Job completed

Embedding generation

Vector storage

LLM request

Fallback provider

Worker failure

Retry

Avoid excessive logging.

---

# Configuration

Never hardcode

API keys

Database URLs

Secrets

Ports

Model names

Use environment variables.

---

# Security

Always validate

ZIP uploads

file paths

user input

JWT

workspace ownership

Protect against

Zip Slip

path traversal

oversized uploads

invalid MIME types

---

# Database Rules

Use PostgreSQL for structured data.

Use Qdrant for vector search.

Never duplicate information unnecessarily.

Prefer normalized schemas.

---

# API Design

RESTful endpoints.

Consistent naming.

Consistent status codes.

Consistent error responses.

Validate all input.

---

# Testing Philosophy

Every phase must include

Unit Tests

Integration Tests

Manual Tests

Edge Cases

Regression Tests

A feature is incomplete without tests.

---

# Performance

Never block HTTP requests with expensive work.

Long-running operations must execute in background workers.

Cache where beneficial.

Batch expensive operations.

Avoid unnecessary database queries.

---

# Documentation

Every module should include

Purpose

Responsibilities

Dependencies

Inputs

Outputs

Every public function should be self-explanatory.

Add comments only when necessary.

---



# Code Review Checklist

Before considering any phase complete:

□ Does every module have a single responsibility?

□ Is there duplicated code?

□ Can naming improve?

□ Is logging sufficient?

□ Is error handling complete?

□ Are tests passing?

□ Are architectural boundaries respected?

□ Is the implementation scalable?

□ Is the code readable?

□ Does it match the specification?

---

# Teaching Mode

While implementing, always explain

- Why the code exists.
- Why this design was chosen.
- Alternative approaches.
- Trade-offs.
- Scalability implications.
- Production considerations.
- Interview-relevant concepts.

Assume the goal is not only to build the software but also to teach software engineering.

---

# Self Review

At the end of every implementation phase provide

Completed tasks

Files created

Files modified

Architecture changes

Tests executed

Known limitations

Possible improvements

Then stop and wait for approval before continuing.

---

# Architectural Discipline

Never silently change

folder structure

database schema

API contracts

service boundaries

technology choices

If a better approach is discovered

Explain

- current limitation
- proposed solution
- advantages
- disadvantages

Wait for approval before implementing.

---

# Final Principle

Build the system as if it will eventually serve thousands of users.

Every engineering decision should make future scaling easier without making Version 1 unnecessarily complex.