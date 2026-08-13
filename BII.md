BUSINESS KNOWLEDGE INFRASTRUCTURE
=================================

IMPLEMENTATION STATUS — PHASE 5
-------------------------------

This document describes target architecture and contracts. Repository implementation
is an internal local protocol demo only. It uses local plaintext files, SQLite/WAL
and FTS5 reference paths, lexical search, an API handler factory, injected ACLs, and
synthetic data. It has no production identity, encryption, authoritative ledger,
durable outbox, atomic backup/restore, monitoring, complete source-scoped deletion,
complete provenance, email connector, or attachment extraction.

### Phase 5 status

Stable delivered spine: versioned envelopes and canonical changes; identity
namespace fields; revision/idempotency handling; provenance and permission links;
ledger, state, projection, query, and capability contracts; and replay-shaped
reference orchestration. Demo reuses local-file, plaintext, SQLite, ledger, state,
projection, lexical, ACL, and audit adapters. Composition boundaries do not imply
production isolation or atomicity. QA/BDD/SRE evidence uses checked-in test-manifest provenance.
Local synthetic protocol-demo is usable for contract demonstrations only.

**Real-data pilot: NO-GO.** Blockers: ledger authority/outbox, namespace/auth
isolation, replay/checkpoints, purge/recovery, API/UI integration, and observability.

Do not interpret target diagrams or future-facing contract lists below as delivered
capability. See `docs/architecture.md` for node mapping, `docs/pilot-readiness.md`, and
`docs/runbook.md` for implementation-verified behavior, limitations, NO-GO blockers,
and remediation steps.

GOAL
----

Create a business-independent knowledge infrastructure.

The business type is configuration.

Every major mechanism is an implementation behind a stable contract.

Dependency injection selects implementations.

The core does not depend on:

- Business type
- Source system
- Connector technology
- Synchronization mechanism
- Storage technology
- Vector database
- Search engine
- Embedding model
- LLM provider
- Output interface

HIGH-LEVEL PIPELINE
-------------------

┌───────────────────┐
│ INPUT │
│ Business systems │
└─────────┬─────────┘
│
▼
┌───────────────────┐
│ CONNECTOR │
│ Acquire changes │
└─────────┬─────────┘
│
│ RawRecord stream
▼
┌───────────────────┐
│ CANONICALIZER │
│ Interpret records │
└─────────┬─────────┘
│
│ CanonicalObject stream
▼
┌───────────────────┐
│ CANONICAL MODEL │
│ Business knowledge│
└─────────┬─────────┘
│
▼
┌──────────────────────────────────────────────┐
│ KNOWLEDGE ENGINE │
│ │
│ Store │
│ Project │
│ Index │
│ Secure │
│ Search │
│ Retrieve │
│ Relate │
│ Track provenance │
└─────────┬────────────────────────────────────┘
│
│ Query contracts
▼
┌───────────────────┐
│ OUTPUT │
│ Consumers │
└───────────────────┘

INPUT
=====

An input is any source of business information.

Examples:

┌──────────────────────────────┐
│ Email │
│ CRM │
│ Accounting │
│ E-commerce │
│ Shared drives │
│ Databases │
│ Spreadsheets │
│ Documents │
│ Websites │
│ Chat │
│ Calendars │
│ Inventory │
│ ERP │
│ Support systems │
│ Supplier systems │
│ Internal applications │
│ Local files │
└──────────────────────────────┘

The Knowledge Engine does not understand these systems.

Connectors isolate source-specific behavior.

CONNECTOR LAYER
===============

                         ┌──────────────────┐

Email ──────────────────►│ │
CRM ────────────────────►│ │
Accounting ─────────────►│ CONNECTOR │
Shop ───────────────────►│ LAYER │
Files ──────────────────►│ │
Database ───────────────►│ │
└────────┬─────────┘
│
▼
RawRecord

CONNECTOR CONTRACT
------------------

A connector can implement operations such as:

authenticate
discover
read
sync
watch
resume
delete
readMetadata
readPermissions
mapIdentity
getCheckpoint

A connector can use any synchronization mechanism.

Examples:

┌──────────────────┐
│ Polling │
│ Webhooks │
│ WebSocket │
│ Change feeds │
│ Event streams │
│ File watching │
│ Batch imports │
│ CDC │
└──────────────────┘

The mechanism does not matter above this boundary.

LOGUX-LIKE VIEW
---------------

A useful way to think about the connector boundary is:

External system
│
│ changes
▼
Connector
│
│
▼
┌────────────────────────────┐
│ CHANGE STREAM │
│ │
│ create │
│ update │
│ delete │
│ permission-change │
│ relationship-change │
└──────────────┬─────────────┘
│
▼
Canonicalizer

The source could produce changes through WebSocket.

Another source could use polling.

Another could use webhooks.

Another could provide a database change feed.

All produce the same conceptual change stream.

RAW RECORD
==========

The connector emits a source-neutral envelope.

Example:

RawRecord
│
├── source
│ ├── connectorId
│ ├── sourceType
│ └── sourceInstance
│
├── sourceRecordId
│
├── recordType
│
├── operation
│ ├── create
│ ├── update
│ └── delete
│
├── content
│
├── metadata
│
├── timestamps
│
├── permissions
│
├── relationships
│
└── syncState

The raw record preserves provenance.

It does not need to represent business meaning.

CANONICALIZATION
================

RawRecord
│
▼
┌─────────────────────────────┐
│ CANONICALIZER │
│ │
│ Source data │
│ ↓ │
│ Interpret │
│ ↓ │
│ Validate │
│ ↓ │
│ Normalize │
│ ↓ │
│ Establish relationships │
└──────────────┬──────────────┘
│
▼
Canonical Objects

Canonicalizers are implementations.

Canonicalizer
│
├── GenericCanonicalizer
├── CommerceCanonicalizer
├── SalesCanonicalizer
├── AccountingCanonicalizer
├── ManufacturingCanonicalizer
└── CustomCanonicalizer

CANONICAL MODEL
===============

The canonical model should stay small.

It describes knowledge.

It does not describe one industry.

CORE CONCEPTS
-------------

CanonicalObject
│
├── Entity
├── Relationship
├── Document
├── Event
├── Observation
├── Attribute
├── Source
├── Identity
└── Permission

DOMAIN OBJECTS
--------------

Domain concepts are implementations or specializations.

Entity
│
├── Customer
├── Lead
├── Product
├── Supplier
├── Employee
├── Machine
└── InventoryItem

Event
│
├── OrderPlaced
├── PaymentReceived
├── CustomerContacted
├── ProductShipped
└── InventoryChanged

Document
│
├── Contract
├── Invoice
├── Email
├── ProductSpecification
├── Policy
└── SupplierDocument

EXAMPLE
-------

Shopify record

{
product_id: 123,
title: "...",
vendor: "...",
...
}

        │
        ▼

ShopifyConnector

        │
        ▼

RawRecord

        │
        ▼

CommerceCanonicalizer

        │
        ▼

Entity<Product>

        │
        ├── source = Shopify
        ├── sourceId = 123
        ├── attributes
        ├── relationships
        ├── permissions
        └── provenance

CANONICAL MODEL IS THE SOURCE OF MEANING
========================================

This distinction is important.

The canonical object is not necessarily the retrieval document.

Instead:

                     Canonical Object
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
         Relational     Document      Graph
         projection     projection    projection
              │            │            │
              ▼            ▼            ▼
             SQL        Full text    Relations
              │
              │            │
              │            ▼
              │          Chunks
              │            │
              │            ▼
              │        Embeddings
              │            │
              ▼            ▼
           Structured    Vector
             search      search

This is where the Cerebras-style document approach fits.

A canonical object can produce a document representation.

Example:

Canonical Customer
│
├── id
├── name
├── company
├── orders
├── conversations
├── assigned salesperson
└── relationships

        │
        ▼

Document Projection

"Customer Acme Corp
Account owner: Jane Smith
Last order: ...
Products purchased: ...
Recent conversations: ..."

        │
        ├──────────────► Full-text index
        │
        ├──────────────► Chunks
        │                    │
        │                    ▼
        │                Embeddings
        │                    │
        │                    ▼
        │                Vector index
        │
        └──────────────► Retrieval document

The document is therefore a projection.

It does not need to be the canonical model.

PROJECTION LAYER
================

                         Canonical Model
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
        Structured         Documents         Relations
        Projection         Projection        Projection
             │                 │                 │
             ▼                 ▼                 ▼
        Relational DB      Object Store      Graph Store
                               │
                               ▼
                         Document Parser
                               │
                               ▼
                             Chunks
                               │
                  ┌────────────┴────────────┐
                  │                         │
                  ▼                         ▼
              Full Text                 Embeddings
                  │                         │
                  ▼                         ▼
             Search Index              Vector Index

DOCUMENT PROCESSING
===================

Original document
│
▼
┌─────────────────┐
│ INGEST │
└────────┬────────┘
▼
┌─────────────────┐
│ PARSE / EXTRACT │
└────────┬────────┘
▼
┌─────────────────┐
│ NORMALIZE │
└────────┬────────┘
▼
┌─────────────────┐
│ CHUNK / SEGMENT │
└────────┬────────┘
▼
┌─────────────────┐
│ EMBED │
└────────┬────────┘
▼
┌─────────────────┐
│ INDEX │
└─────────────────┘

Derived artifacts remain linked to their source.

Original Document
│
├── TextBlock
├── Table
├── Metadata
├── Chunk
├── Entity
├── Relationship
├── Embedding
└── Summary

Every derived artifact keeps provenance.

KNOWLEDGE ENGINE
================

The Knowledge Engine coordinates knowledge operations.

It should not contain infrastructure implementations.

                    ┌─────────────────────────────┐
                    │      KNOWLEDGE ENGINE       │
                    │                             │
                    │ Storage orchestration       │
                    │ Indexing                    │
                    │ Search                      │
                    │ Retrieval                   │
                    │ Relationship traversal      │
                    │ Document processing         │
                    │ Chunking                    │
                    │ Embedding                   │
                    │ Ranking                     │
                    │ Permission filtering        │
                    │ Provenance tracking         │
                    │ Deduplication               │
                    │ Version handling            │
                    │ Deletion handling           │
                    │ Change tracking             │
                    │ Query planning              │
                    │ Context construction        │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                            Query Contracts

KNOWLEDGE ENGINE CONTRACTS
==========================

The engine depends on interfaces.

KnowledgeStore
DocumentStore
VectorStore
RelationshipStore
EventStore

Embedder
Retriever
Reranker
InferenceProvider

PermissionEngine
IdentityResolver

DocumentParser
Chunker
Extractor

ProvenanceStore

The composition root supplies implementations.

DEPENDENCY INJECTION
====================

                     Application Core
                           │
                 depends on contracts
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      Connector      KnowledgeStore     Embedder
       contract         contract         contract
          ▲                ▲                ▲
          │                │                │
    implementation    implementation    implementation

Example deployment:

Connector
= GoogleDriveConnector

KnowledgeStore
= PostgresKnowledgeStore

VectorStore
= PgVectorStore

DocumentStore
= LocalDocumentStore

Embedder
= LocalEmbedder

Retriever
= HybridRetriever

InferenceProvider
= LocalInferenceProvider

Another deployment can replace every implementation.

The core remains unchanged.

SEARCH AND RETRIEVAL
====================

A query does not need to use one retrieval method.

Example:

                         Query
                           │
                           ▼
                    Query Planner
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      Structured       Full-text         Vector
        query            search           search
          │                │                │
          └────────────────┼────────────────┘
                           │
                           ▼
                       Candidates
                           │
                           ▼
                     Permission Filter
                           │
                           ▼
                         Rerank
                           │
                           ▼
                    Evidence Bundle
                           │
                           ▼
                        Output

RELATIONSHIP RETRIEVAL
======================

Relationships allow queries beyond document similarity.

Example:

Customer
│
├── placed ─────────► Order
│ │
│ └── contains ──► Product
│
├── assigned-to ────► Salesperson
│
├── sent ───────────► Email
│
└── belongs-to ─────► Company

A question such as:

"What products did customers assigned to Sarah buy last quarter?"

can use relationships and structured data.

It does not need to depend only on vector search.

PERMISSIONS
===========

Permissions travel with knowledge.

Source
│
▼
Connector
│
│ read source permissions
▼
RawRecord
│
▼
CanonicalObject
│
│ preserve permissions
▼
Projection
│
│ preserve permissions
▼
Index
│
▼
Retrieval
│
▼
Permission Filter
│
▼
Authorized Result

Permission is not only a UI concern.

It is part of the knowledge model.

IDENTITY
========

External identities map to internal identities.

Microsoft user ────┐
Google user ───────┤
CRM user ──────────┼──► Internal Identity
Sales system user ─┤
Local account ─────┘

The internal identity controls knowledge access.

PROVENANCE
==========

Every result should provide a chain.

Result
│
▼
Derived Artifact
│
▼
Canonical Object
│
▼
Raw Record
│
▼
Connector
│
▼
External Source

The system should answer:

Where did this come from?

When did it change?

Which source produced it?

Which transformation created it?

Which source document supports it?

Which permissions apply?

Is the source still present?

OUTPUT
======

The Knowledge Engine exposes contracts.

                         Knowledge Engine
                               │
                               ▼
                         Query Interface
                               │
             ┌─────────────────┼─────────────────┐
             │                 │                 │
             ▼                 ▼                 ▼
           Search             MCP               API
             │                 │                 │
             ▼                 ▼                 ▼
          Web UI            Agents          Applications

Additional outputs:

Chat
Sales assistant
Reporting
Business intelligence
Automation
CLI
Internal applications
External applications

OUTPUT CONTRACTS
================

Possible operations:

search(query)

retrieve(query)

getEntity(id)

getRelationships(id)

getDocument(id)

getSource(id)

getTimeline(id)

getEvidence(id)

getPermissions(id)

LLM IS OPTIONAL
===============

The architecture does not require an LLM.

                         Knowledge Engine
                               │
                    ┌──────────┼──────────┐
                    │          │          │
                    ▼          ▼          ▼
                  Search      API        MCP
                                           │
                                           ▼
                                     LLM / Agent

The LLM is a consumer.

It is not the knowledge system.

MODEL ABSTRACTIONS
==================

Model contracts can include:

Embedder
Reranker
Classifier
Extractor
InferenceProvider

Implementations can be:

Local
Remote
Hybrid

The Knowledge Engine does not care which implementation runs.

CHANGE PROPAGATION
==================

This is where the Logux comparison becomes useful.

Source changes
│
▼
Connector
│
▼
Change Record
│
▼
Canonicalizer
│
▼
Canonical Change
│
▼
Knowledge Engine
│
├── update canonical state
│
├── update relational projection
│
├── update document projection
│
├── update graph relationships
│
├── update full-text index
│
├── update embeddings
│
└── update permissions
│
▼
Knowledge is synchronized

A source update does not require complete re-ingestion.

Only affected projections need updates.

DELETE PROPAGATION
==================

Source delete
│
▼
Connector
│
▼
Delete RawRecord
│
▼
Canonicalizer
│
▼
Canonical deletion
│
▼
Knowledge Engine
│
├── tombstone entity
├── remove search entry
├── remove vectors
├── update relationships
├── invalidate caches
└── preserve audit history

COMPLETE SYSTEM
===============

EXTERNAL BUSINESS SYSTEMS
=========================

Email CRM Accounting Shop Files DB Website ERP
│ │ │ │ │ │ │ │
└──────┴────────┴─────────┴──────┴──────┴──────┴───────┘
│
▼

                    CONNECTOR LAYER
             ┌──────────────────────────┐
             │ Authentication           │
             │ Discovery                │
             │ Polling                  │
             │ Webhooks                 │
             │ WebSockets               │
             │ Change feeds             │
             │ Incremental sync         │
             │ Permission discovery     │
             │ Identity mapping         │
             │ Checkpoint management    │
             └────────────┬─────────────┘
                          │
                          ▼

                     RAW RECORDS
             ┌──────────────────────────┐
             │ Source                   │
             │ Source record ID         │
             │ Operation                │
             │ Content                  │
             │ Metadata                 │
             │ Permissions              │
             │ Relationships            │
             │ Timestamp                │
             │ Sync state               │
             └────────────┬─────────────┘
                          │
                          ▼

                    CANONICALIZER
             ┌──────────────────────────┐
             │ Interpret                │
             │ Validate                 │
             │ Normalize                │
             │ Relate                   │
             │ Preserve provenance      │
             └────────────┬─────────────┘
                          │
                          ▼

                    CANONICAL MODEL
             ┌──────────────────────────┐
             │ Entity                   │
             │ Relationship             │
             │ Document                 │
             │ Event                    │
             │ Observation              │
             │ Attribute                │
             │ Source                   │
             │ Identity                 │
             │ Permission               │
             └────────────┬─────────────┘
                          │
                          ▼

                    KNOWLEDGE ENGINE
       ┌──────────────────┼──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼

STRUCTURED DOCUMENT RELATIONSHIP
PROJECTION PROJECTION PROJECTION
│ │ │
▼ ▼ ▼
Relational Documents Graph
Store │ Store
│
▼
Parse / Extract
│
▼
Chunks
│
┌─────────┴─────────┐
│ │
▼ ▼
Full Text Embeddings
│ │
▼ ▼
Search Index Vector Index

       │                  │                  │
       └──────────────────┼──────────────────┘
                          │
                          ▼

                       RETRIEVAL
             ┌──────────────────────────┐
             │ Query planning           │
             │ Structured search        │
             │ Full-text search         │
             │ Vector search            │
             │ Relationship traversal   │
             │ Permission filtering     │
             │ Ranking                  │
             │ Evidence construction    │
             └────────────┬─────────────┘
                          │
                          ▼

                    QUERY CONTRACTS
             ┌──────────────────────────┐
             │ search                   │
             │ retrieve                 │
             │ getEntity                │
             │ getRelationships         │
             │ getDocument              │
             │ getSource                │
             │ getTimeline              │
             │ getEvidence              │
             │ getPermissions           │
             └────────────┬─────────────┘
                          │
                          ▼

                       OUTPUTS
       ┌──────────────────┼──────────────────┐
       │                  │                  │
       ▼                  ▼                  ▼
      Web                MCP                API
       │                  │                  │
       │             ┌────┴────┐             │
       │             ▼         ▼             │
       │           Agent      LLM            │
       │                                      │
       └──────────────────┬───────────────────┘
                          │
                          ▼
                  BUSINESS USERS

CORE PRINCIPLE
==============

                         CONTRACTS
                             │
                             ▼
                           CORE
                             │
                             ▼
                     DEPENDENCY INJECTION
                             │
             ┌───────────────┼───────────────┐
             │               │               │
             ▼               ▼               ▼
        Connector       Storage         Model
     implementation  implementation  implementation
             │               │               │
             └───────────────┼───────────────┘
                             │
                             ▼
                         Deployment

Business type = configuration

Source integration = implementation

Synchronization = implementation

Canonicalization = implementation

Storage = implementation

Indexing = implementation

Retrieval = implementation

Models = implementation

Outputs = implementation

Contracts = stable boundaries

Canonical knowledge = portable

Knowledge Engine = orchestration and policy
