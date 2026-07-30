# Workspace Intelligence Engine (WIE)
### Software Architecture & Technical Specification
Version: 1.0
Status: Design Approved
Author: Ekansh Sethia

---

# 1. Project Vision

## Goal

Workspace Intelligence Engine (WIE) is an AI-powered web application that enables users to upload an entire workspace (ZIP folder containing documents and images), semantically understand its contents, and interact with it through a natural language interface.

Unlike traditional "Chat with PDF" applications, WIE is designed as a **workspace operating system** where the chat interface serves as the primary interaction method while the backend acts as an intelligent knowledge engine.

---

# 2. Problem Statement

Knowledge is scattered across

- PDFs
- DOCX
- TXT
- PPTX
- Images
- Notes
- Diagrams

Finding information manually is slow.

Existing RAG applications generally:

- work with one document
- provide poor organization
- ignore relationships between files
- lack workspace-level understanding

WIE solves this by building a semantic representation of an entire workspace.

---

# 3. V1 Objectives

The first version must support:

✔ ZIP upload

✔ Workspace extraction

✔ PDF parsing

✔ DOCX parsing

✔ TXT parsing

✔ Markdown parsing

✔ PPTX parsing

✔ Image OCR

✔ Image Captioning

✔ Chunking

✔ Embedding generation

✔ Semantic Search

✔ Workspace Summary

✔ File Summaries

✔ Chat

✔ Citations

✔ Merge multiple documents into one text file

---

# 4. Non Goals

The following are intentionally excluded from V1.

- Repository Analysis
- Code Parsing
- Tree-sitter
- Git Integration
- AST Analysis
- Repository Dependency Graph
- Fine-tuned Models
- Multi-user Collaboration
- Workspace Sharing
- Cloud Storage Integration

These belong to future versions.

---

# 5. Users

Primary users

- Students
- Researchers
- Software Engineers
- Professionals

---

# 6. Core Philosophy

The LLM is NOT the system.

The LLM is one component of the system.

Most work should be performed without invoking an LLM whenever possible.

Examples

✔ Find all PDFs

✔ Merge files

✔ List documents

✔ Metadata search

These should not require an LLM.

The LLM should only be used for reasoning and generation.

---

# 7. High Level Architecture

                    React Frontend
                           │
                           │
                    FastAPI Backend
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
 Workspace Service                      Chat Service
        │                                     │
 Upload Queue                        Intent Router
        │                                     │
 Worker Pool                    Metadata Search
        │                                     │
 Parsing Pipeline                 Vector Search
        │                                     │
 Embedding Service               Context Builder
        │                                     │
      Qdrant                    LLM Gateway
        │                                     │
     PostgreSQL              Response Formatter

---

# 8. Technology Stack

Frontend

- Next.js
- React
- TypeScript
- TailwindCSS
- shadcn/ui

Backend

- FastAPI

Authentication

- JWT

Database

- PostgreSQL

Vector Database

- Qdrant

Queue

- Redis

Workers

- Celery

Embeddings

- BAAI/bge-small-en-v1.5

OCR

- PaddleOCR

Image Captioning

- Florence-2 (or equivalent)

LLM Providers

- OpenAI
- Gemini

Deployment

- Docker

---

# 9. Folder Structure

backend/

    api/

    authentication/

    workspace/

    parser/

    embeddings/

    vector_store/

    metadata/

    retrieval/

    llm/

    workers/

    models/

    services/

    utils/

frontend/

docker/

tests/

docs/

---

# 10. Layered Architecture

The application is divided into independent layers.

Layer 1

Authentication

Responsibilities

- Login
- Signup
- JWT
- User Management

Output

Authenticated User

---------------------

Layer 2

Workspace Upload

Responsibilities

- Receive ZIP
- Validate
- Save
- Create Job

Output

Workspace Job

---------------------

Layer 3

Workspace Extraction

Responsibilities

- Extract ZIP
- Ignore unsupported files
- Validate paths
- Prevent Zip Slip
- Build file tree

Output

Workspace Directory

---------------------

Layer 4

Document Parsing

Responsibilities

Convert documents into plain text.

Supported

PDF

DOCX

TXT

Markdown

PPTX

Images

Output

Raw Text

---------------------

Layer 5

Chunking

Responsibilities

Split parsed text into semantic chunks.

Store metadata.

Output

Chunks

---------------------

Layer 6

Embedding Generation

Responsibilities

Generate embeddings.

Store embedding vectors.

Output

Vector IDs

---------------------

Layer 7

Metadata Generation

Responsibilities

Generate

- file summary
- keywords
- topics
- page count

Output

Metadata

---------------------

Layer 8

Workspace Summary

Responsibilities

Generate

Workspace summary

Topics

Statistics

Document summaries

Output

Workspace Metadata

---------------------

Layer 9

Retrieval

Responsibilities

Metadata Search

Semantic Search

Ranking

Context Building

Output

Relevant Context

---------------------

Layer 10

LLM Gateway

Responsibilities

Provider Selection

Retry

Fallback

Logging

Streaming

Output

Generated Answer

---------------------

Layer 11

Response Generation

Responsibilities

Generate

Answer

Citations

Suggested Questions

Download Links

---

# 11. Upload Flow

User Uploads ZIP

↓

Validate

↓

Store

↓

Create Workspace

↓

Queue Job

↓

Return Success

↓

Background Worker Starts

↓

Extract

↓

Parse

↓

Chunk

↓

Embed

↓

Generate Metadata

↓

Generate Workspace Summary

↓

Complete

---

# 12. Chat Flow

User Query

↓

Intent Detection

↓

Metadata Search

↓

Vector Search

↓

Context Builder

↓

LLM Gateway

↓

Response

↓

Citations

---

# 13. Intent Categories

Every query should first be classified.

Supported Intents

Metadata Search

Examples

List PDFs

List images

Find all files

--------

Semantic Search

Examples

Which files discuss SQL?

Find Operating System notes.

--------

Summarization

Summarize Workspace

Summarize Document

--------

Actions

Merge documents

Export text

Generate revision notes

--------

Reasoning

Explain ACID

Compare normalization forms

---

# 14. Supported Actions

Search Documents

Summarize

Merge Documents

Generate Revision Notes

Generate Quiz

Export TXT

Export Markdown

---

# 15. Parsing Strategy

Each file type has its own parser.

Abstract Parser

↓

PDF Parser

DOCX Parser

TXT Parser

Markdown Parser

PPT Parser

Image Parser

All parsers return

Document Object

Document Object

- filename
- text
- metadata

---

# 16. Chunking Strategy

Chunk Size

~500 tokens

Overlap

~100 tokens

Chunk Metadata

Workspace ID

Document ID

Filename

File Type

Page Number

Chunk Index

---

# 17. Metadata Schema

Every document stores

Document ID

Workspace ID

Filename

Extension

Hash

Summary

Keywords

Topics

Chunk Count

Page Count

Created At

Updated At

---

# 18. Workspace Summary

Workspace Summary contains

Document Count

Image Count

Total Pages

Total Chunks

Detected Topics

Detected Keywords

Workspace Summary

Document Summaries

---

# 19. Retrieval Strategy

Pipeline

Query

↓

Intent Classification

↓

Metadata Filter

↓

Semantic Search

↓

Top K Retrieval

↓

Context Builder

↓

LLM

↓

Answer

---

# 20. LLM Gateway

Responsibilities

Retry

Fallback

Streaming

Caching

Provider Selection

Logging

Rate Limit Handling

Supported Providers

OpenAI

Gemini

Future

Ollama

Anthropic

---

# 21. Error Handling

Invalid ZIP

Unsupported File

Corrupted Document

OCR Failure

Embedding Failure

LLM Failure

Rate Limit

Worker Failure

Duplicate Workspace

---

# 22. Security

JWT Authentication

Workspace Isolation

File Size Limits

ZIP Validation

Zip Slip Protection

Temporary File Cleanup

Input Sanitization

API Rate Limiting

---

# 23. Testing Strategy

Every layer must contain

Unit Tests

Integration Tests

Manual Tests

Performance Tests

Edge Cases

Examples

Upload Corrupted ZIP

Expected

400

--------

Upload Empty ZIP

Expected

Validation Error

--------

Upload Duplicate Workspace

Expected

Reuse Existing Data

--------

OCR Failure

Expected

Graceful Skip

--------

LLM Failure

Expected

Fallback

---

# 24. Performance Optimizations

Background Workers

Caching

Batch Embedding

Streaming Responses

Lazy Workspace Loading

Metadata Search before Semantic Search

LLM as Last Resort

---

# 25. Future Roadmap

## Version 1

Workspace Intelligence

Documents

Images

Search

Chat

Workspace Summary

Merge Documents

Revision Notes

---

## Version 2

Repository Intelligence

Tree-sitter

Code Chunking

Dependency Graph

Repository Search

Function Search

Explain Repository

---

## Version 3

Workspace Actions

Google Drive

GitHub

OneDrive

Slack

Browser Extension

Incremental Indexing

Workspace Synchronization

---

# 26. Engineering Principles

1. Every layer should be independently testable.

2. Every service should have a single responsibility.

3. Prefer composition over tightly coupled modules.

4. The LLM is the last component to be invoked.

5. All expensive operations must run asynchronously.

6. Every generated answer must contain citations.

7. Design for extensibility rather than premature complexity.

8. The architecture should support future repository analysis without requiring major redesign.

9. Every design decision should prioritize maintainability over cleverness.

10. Every feature must justify its computational cost.

---

# 27. Definition of Done

A feature is complete only if it includes:

- Production-quality implementation
- Unit tests
- Integration tests
- Error handling
- Logging
- Documentation
- Manual testing checklist
- Performance considerations