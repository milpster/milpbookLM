# 20 — Internal Extension Boundaries

## 1. Goal

Core subsystems need clean internal interfaces so providers/connectors can be replaced or added without forking domain code. **A third-party plugin SDK, plugin marketplace, dynamic plugin loader or MCP-based extension ecosystem is not a baseline requirement.**

## 2. Internal extension boundaries

The implementation should keep narrow interfaces for the places where variation is already required by the product:

- **source/connector adapter** — acquires a supported source and produces canonical-document-compatible input plus refresh/access-restriction metadata where relevant;
- **model/capability adapter** — exposes LLM, embedding, reranking, speech or media capabilities through the model platform;
- **agent tool** — a controlled built-in capability with a schema and authorization policy;
- **artifact recipe/renderer** — implements one of the documented Studio artifact families;
- **exporter** — renders supported artifact/source representations to portable files.

These are internal contracts first. They do not need runtime discovery or third-party packaging in the parity roadmap.

## 3. Versioning

Interfaces that persist data or cross process boundaries MUST be versioned where necessary. Pure in-process interfaces can evolve with the application until there is a demonstrated external compatibility requirement.

## 4. Explicitly deferred ecosystem work

The following are explicitly post-parity and should not influence initial implementation complexity:

- a public plugin SDK or marketplace;
- untrusted third-party server plugins;
- dynamic UI-plugin loading;
- MCP or similar protocols as a general extension layer;
- user-defined artifact schema/recipe builders.

If such features are later justified, they should adapt to the existing internal boundaries rather than redefine the core architecture.
