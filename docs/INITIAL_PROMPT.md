# ROLE

You are an elite Principal Software Architect, AI Systems Architect, Staff Engineer, Enterprise Architect, Political Intelligence expert, GIS expert, Data Engineer, UX Architect, Security Architect, and Product Strategist.

Your task is to design a **world-class Political Intelligence Platform (PIP)**.

Do **NOT** optimize for simplicity.

Optimize for:

* scalability
* modularity
* maintainability
* observability
* extensibility
* AI-first architecture
* production readiness
* enterprise quality
* security
* explainability
* evidence-based reasoning
* long-term evolution

Think like the architects of Palantir, Google, Microsoft, Datadog, Notion, GitHub, Stripe and OpenAI combined.

Challenge every assumption.

Whenever you identify a better architecture than the one implied below, explain why and propose it.

---

# OBJECTIVE

Design the complete architecture of a platform that continuously discovers, aggregates, verifies, prioritizes and explains **all problems affecting citizens of a geographical constituency** (for example: A' Thessaloniki).

The platform will support politicians, policy advisors, researchers and campaign teams by providing an always up-to-date understanding of local issues.

The goal is **not political persuasion or voter profiling**, but structured situational awareness, evidence management, issue tracking and policy planning based on publicly available information and voluntarily submitted reports.

The output should be a production-grade software architecture suitable for implementation.

---

# GENERAL PRINCIPLES

The system should transform

Raw Data

↓

Information

↓

Knowledge

↓

Evidence

↓

Intelligence

↓

Actionable Recommendations

Every statement must be traceable back to evidence.

Every recommendation must explain WHY it exists.

Every detected issue must have supporting sources.

Nothing should be a black box.

---

# DESIGN REQUIREMENTS

Design every subsystem in detail.

For every module include:

Purpose

Responsibilities

Inputs

Outputs

Dependencies

Failure modes

Scaling strategy

Caching

Security

Monitoring

Testing strategy

Deployment strategy

API

Database schema

Extensibility

Future evolution

---

# CORE MODULES

Design the following as independent services.

## 1. Source Registry

Maintain every available source.

Examples:

* news websites
* RSS
* government portals
* municipal websites
* open data portals
* consultation portals
* publicly available social media content accessed through permitted mechanisms
* PDF repositories
* meeting minutes
* parliamentary documents
* public procurement
* legislation
* budget documents
* court decisions
* ombudsman reports
* citizen reports
* mobile app submissions
* surveys
* GIS datasets
* satellite imagery
* environmental sensors
* weather
* traffic
* transportation
* public APIs

Support plugin architecture.

---

## 2. Data Collection Layer

Design collectors with

Scheduling

Retry

Authentication

Rate limiting

Deduplication

Incremental updates

Versioning

Queueing

Monitoring

Health checks

Dead-letter queues

---

## 3. Document Repository

Support

PDF

DOCX

TXT

HTML

XML

Images

Videos

Audio

ZIP

Scanned documents

Meeting recordings

Store

metadata

versions

hashes

OCR status

language

source

permissions

---

## 4. OCR Pipeline

Support

Scanned PDFs

Photos

Mobile uploads

Historical archives

Pipeline

OCR

↓

Cleaning

↓

Layout reconstruction

↓

Table extraction

↓

LLM correction

↓

Structured JSON

---

## 5. Speech Pipeline

Meetings

Municipal councils

Interviews

Podcasts

Public speeches

Voice notes

Pipeline

Speech-to-text

↓

Speaker diarization

↓

Summarization

↓

Entity extraction

↓

Problem extraction

---

## 6. NLP Extraction Engine

Extract

Problem

Location

Organization

Authority

Person (where appropriate and necessary)

Date

Urgency

Emotion

Requested action

Evidence

Confidence

Related legislation

Affected population

Affected infrastructure

Financial impact

Environmental impact

---

## 7. Geolocation Engine

Convert

Addresses

Neighborhoods

Municipal districts

GPS

Landmarks

Into

Latitude

Longitude

Administrative boundaries

Election districts

Statistical regions

Support PostGIS.

---

## 8. Knowledge Graph

Design a graph connecting

Problems

People (where appropriate)

Organizations

Authorities

Infrastructure

Projects

Budgets

Laws

Locations

Meetings

Documents

Media

Time

Design ontology.

Explain relationships.

---

## 9. Problem Engine

Each problem should contain

Unique ID

Title

Description

Category

Subcategory

Status

First seen

Last seen

Severity

Frequency

Trend

Evidence score

Confidence score

Verification status

Related documents

Related locations

Responsible authority

Potential solutions

Estimated cost

Priority

---

## 10. Constituency Engine

Represent

Districts

Neighborhoods

Communities

Schools

Hospitals

Businesses

Associations

Transport

Public buildings

Infrastructure

Demographics (aggregated, non-personal)

---

## 11. GIS Engine

Design layered maps.

Possible layers

Roads

Lighting

Parking

Flood risk

Traffic

Air quality

Noise

Waste

Schools

Hospitals

Construction

Public transport

Green spaces

Population density

Accessibility

---

# AI AGENT LAYER

Design a multi-agent architecture.

Possible agents

Collector Agent

Crawler Agent

OCR Agent

News Agent

Document Agent

Meeting Agent

Policy Agent

Verification Agent

Fact Checking Agent

Evidence Agent

Deduplication Agent

Classification Agent

Trend Detection Agent

Forecasting Agent

Anomaly Detection Agent

Recommendation Agent

Speech Preparation Agent

Report Generator

Dashboard Agent

Semantic Search Agent

Graph Reasoning Agent

Summarization Agent

Alert Agent

Quality Assurance Agent

Evaluation Agent

Router Agent

Memory Agent

Planner Agent

For every agent specify

Role

Tools

Memory

Inputs

Outputs

Failure recovery

Evaluation metrics

Interaction protocol

---

# EVIDENCE ENGINE

Design an evidence system.

Every claim must include

Source

Timestamp

Confidence

Independent confirmations

Supporting documents

Supporting media

Historical evolution

Contradictory evidence

Reliability score

Explainability

---

# INTELLIGENCE ENGINE

Design scoring systems

Priority Score

Severity Score

Evidence Score

Confidence Score

Trend Score

Impact Score

Urgency Score

Media Attention Score

Operational Complexity

Estimated Cost

Expected Benefit

Time To Resolve

Policy Leverage Score

Explain all formulas.

---

# RECOMMENDATION ENGINE

Generate

Possible interventions

Administrative actions

Policy proposals

Funding opportunities

Relevant legislation

Comparable case studies

Expected impact

Risks

Dependencies

Success metrics

Every recommendation must cite supporting evidence.

---

# DASHBOARD

Design executive dashboards.

Include

Heat maps

Timelines

Problem clusters

Trend graphs

Alerts

Recent discoveries

Geographical distribution

Evidence explorer

Knowledge graph explorer

AI explanations

Task tracking

---

# SEARCH

Design semantic search.

Examples

"What problems affect young families in Toumba?"

"Show unresolved traffic issues."

"Find issues increasing during the last six months."

Support

Hybrid search

Vector search

Keyword search

Graph search

Geospatial search

---

# MOBILE APPLICATION

Citizen submissions

Photo

Video

Voice

GPS

Offline mode

Progress tracking

Notifications

Issue status

Privacy controls

---

# API

REST

GraphQL

Streaming

MCP

Webhooks

SDK

Authentication

Rate limiting

Versioning

---

# DATABASES

Recommend the optimal databases.

Evaluate

PostgreSQL

PostGIS

Neo4j

Memgraph

OpenSearch

Qdrant

Redis

S3

DuckDB

TimescaleDB

ClickHouse

Object storage

Explain why each database exists.

---

# EVENT-DRIVEN ARCHITECTURE

Design

Kafka or Redpanda

Event sourcing

CQRS

Message queues

Outbox pattern

Saga pattern

Replay

Snapshots

---

# SECURITY

Design

RBAC

ABAC

Encryption

Secrets

Audit logs

GDPR compliance

Privacy by design

Data minimization

Backup

Disaster recovery

Zero trust

Threat modeling

---

# OBSERVABILITY

Metrics

Tracing

Logging

Alerting

Dashboards

SLO

SLI

Error budgets

OpenTelemetry

Prometheus

Grafana

---

# AI ARCHITECTURE

Recommend

LLM routing

Model selection

Prompt versioning

Evaluation framework

Hallucination detection

Grounding

Retrieval

RAG

Knowledge Graph integration

Context engineering

Long-context management

Memory hierarchy

Token optimization

Cost optimization

Latency optimization

Human approval workflows

---

# DEVELOPMENT

Recommend

Monorepo vs Polyrepo

Folder structure

DDD

Hexagonal Architecture

Clean Architecture

Microservices vs Modular Monolith

Testing pyramid

CI/CD

Feature flags

Infrastructure as Code

Docker

Kubernetes

GitHub Actions

Terraform

---

# TECHNOLOGY STACK

Recommend the optimal stack for every layer.

Justify every decision.

---

# ROADMAP

Produce

Phase 1

MVP

Phase 2

Beta

Phase 3

Production

Phase 4

Enterprise

Estimate

Complexity

Risks

Dependencies

Team composition

Timeline

---

# DELIVERABLES

Produce:

1. Executive Summary

2. High-Level Architecture

3. C4 Diagrams (textual)

4. Component Diagrams

5. Sequence Diagrams

6. Data Flow Diagrams

7. Event Flow Diagrams

8. Database Schemas

9. Knowledge Graph Ontology

10. Agent Interaction Diagrams

11. API Specifications

12. Folder Structure

13. Infrastructure Diagram

14. Security Model

15. Deployment Architecture

16. Scalability Strategy

17. Cost Optimization Strategy

18. Monitoring Strategy

19. Disaster Recovery Plan

20. Future Evolution Roadmap

21. Risks and Trade-offs

22. Critical Design Decisions

23. Suggested Open Source Components

24. Benchmark Against Existing Platforms (e.g., Palantir Gotham, ArcGIS, CKAN, OpenSearch-based intelligence platforms)

25. Final Architecture Review with identified weaknesses and proposed improvements.

Do not stop until every subsystem has been fully specified.

Critically review your own design, identify weaknesses, propose improvements, then iterate once more before presenting the final architecture.
