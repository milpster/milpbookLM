# 20 — Internal Extension Interfaces

## Registered ports

Define versioned interfaces for `SourceAdapter`, `Parser`, `CanonicalEnricher`, `Chunker`, `EmbeddingProvider`, `RerankerProvider`, `ModelProvider`, `SearchProvider`, `FetchProvider`, `BrowserProvider`, `ExecutionProvider`, `ArtifactRecipe`, `Renderer`, `BlobStore`, `IdentityProvider` and `NotificationProvider`.

## Contract rules

Each interface owns request/response JSON Schema, error taxonomy, cancellation/deadline semantics, health/capability probing and compatibility tests. Domain/application packages depend only on ports. Adapter-specific configuration is namespaced and never stored inside notebook domain objects.

## Versioning

Additive optional fields are minor revisions; changed meaning/removal is a major revision with an upcaster/migration window. Persist the adapter and contract version with durable outputs. Unknown adapter versions fail visibly rather than guessing.

## Non-goals

Registration is compile/deploy-time and administrator-controlled. There is no downloadable plugin marketplace, arbitrary in-process third-party code or stable public plugin SDK in the baseline.
