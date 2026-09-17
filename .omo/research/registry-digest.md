# Registry Digest — requirements.generated.json + capabilities.generated.json

Source: explore agent ses_f505bfae8ffecoO0AizC9cOu54 (bg_ba82594b), 2026-09-17, deliverable recovered from session log after token-limit loop. Verified checksums stated at end.
Canonical files: milpbookml-implementation-guide/requirements.generated.json (507 records; 16 TECH-* + 491 ARCH-*), capabilities.generated.json (61 records).
NOTE: aggregate class counts differ by ±1 between two independent counts (planner: must_not 78/should 142; agent: must_not 79/should 141 — both sum 507). Plan cites exact ID ranges, not aggregates, so immaterial; flagged for honesty.

**CANONICAL-LABEL CORRECTION (2026-09-17, dual-review round rr-02, oracle defect 6):** `requirements.generated.json` component labels are CANONICAL wherever the Table A grouping or Table D anomaly mappings disagree. Verified against the JSON directly: ARCH-05-001 → domain_model (not deployment), ARCH-14-001 → media_generation (not studio_artifacts), ARCH-01-002..004 → platform_core (not capability_registry). Canonical component totals: platform_core 61, deployment 22, domain_model 21, capability_registry 9, media_generation 16, studio_artifacts 15 (all other rows unchanged; total stays 507). Table A below is preserved as originally derived for traceability; the plan's master index carries the canonical-label rule and the F1 compliance join uses canonical labels. Every ID remains covered by the plan either way.

## TABLE A — per implementation_component (23 distinct; sorted by count desc)
IDs are complete contiguous runs per component (no gaps → no (skip) markers needed).

| component | total | must | must_not | should | should_not | narrative | PR | nightly | RC | review | none | IDs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| platform_core | 58 | 25 | 13 | 8 | 0 | 12 | 46 | 0 | 0 | 0 | 12 | TECH-00-001..003, ARCH-00-001..050, ARCH-01-001, ARCH-03-001..004 |
| testing_release | 52 | 37 | 4 | 9 | 2 | 0 | 0 | 0 | 52 | 0 | 0 | TECH-25-001..002, ARCH-25-001..050 |
| security_privacy | 51 | 29 | 11 | 11 | 0 | 0 | 0 | 51 | 0 | 0 | 0 | ARCH-19-001..051 |
| nonfunctional | 47 | 21 | 3 | 21 | 2 | 0 | 0 | 0 | 47 | 0 | 0 | TECH-21-001..002, ARCH-21-001..045 |
| auth_sharing | 33 | 23 | 6 | 4 | 0 | 0 | 33 | 0 | 0 | 0 | 0 | ARCH-17-001..033 |
| model_platform | 29 | 15 | 3 | 11 | 0 | 0 | 29 | 0 | 0 | 0 | 0 | ARCH-10-001..029 |
| jobs_events | 27 | 12 | 3 | 12 | 0 | 0 | 27 | 0 | 0 | 0 | 0 | ARCH-15-001..027 |
| deployment | 23 | 7 | 5 | 11 | 0 | 0 | 1 | 0 | 22 | 0 | 0 | ARCH-04-001..022, ARCH-05-001 |
| source_ingestion | 20 | 9 | 5 | 4 | 2 | 0 | 0 | 20 | 0 | 0 | 0 | ARCH-06-001..020 |
| domain_model | 20 | 9 | 7 | 3 | 1 | 0 | 20 | 0 | 0 | 0 | 0 | TECH-05-001, ARCH-05-002..020 |
| grounded_chat | 18 | 7 | 4 | 7 | 0 | 0 | 0 | 18 | 0 | 0 | 0 | TECH-09-001, ARCH-09-001..017 |
| code_execution | 18 | 11 | 3 | 3 | 1 | 0 | 18 | 0 | 0 | 0 | 0 | ARCH-12-001..018 |
| studio_artifacts | 16 | 3 | 2 | 11 | 0 | 0 | 0 | 15 | 1 | 0 | 0 | TECH-13-001, ARCH-13-001..014, ARCH-14-001 |
| media_generation | 15 | 8 | 2 | 3 | 2 | 0 | 0 | 0 | 15 | 0 | 0 | ARCH-14-002..016 |
| agentic_research | 13 | 8 | 1 | 4 | 0 | 0 | 13 | 0 | 0 | 0 | 0 | TECH-11-001, ARCH-11-001..012 |
| capability_registry | 12 | 5 | 2 | 5 | 0 | 0 | 12 | 0 | 0 | 0 | 0 | TECH-02-001..002, ARCH-01-002..004, ARCH-02-001..007 |
| knowledge_indexing | 11 | 6 | 1 | 4 | 0 | 0 | 0 | 11 | 0 | 0 | 0 | ARCH-08-001..011 |
| web_client | 11 | 7 | 2 | 2 | 0 | 0 | 11 | 0 | 0 | 0 | 0 | ARCH-16-001..011 |
| canonical_provenance | 10 | 7 | 1 | 2 | 0 | 0 | 10 | 0 | 0 | 0 | 0 | TECH-07-001..002, ARCH-07-001..008 |
| evaluation | 9 | 7 | 0 | 2 | 0 | 0 | 0 | 0 | 9 | 0 | 0 | TECH-18-001, ARCH-18-001..008 |
| roadmap | 6 | 4 | 1 | 1 | 0 | 0 | 0 | 0 | 6 | 0 | 0 | ARCH-22-001..006 |
| adapter_contracts | 4 | 2 | 0 | 1 | 1 | 0 | 4 | 0 | 0 | 0 | 0 | ARCH-20-001..004 |
| decisions | 4 | 2 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | ARCH-23-001..004 |

## TABLE B — capabilities (61 rows; CP=CAP-PROFILE-001, PG=PHASE-GATE-001, PA=PARITY-ACCEPTANCE-001)

| id | phase | workstream | classification | feature_flag | test groups | manual |
|---|---|---|---|---|---|---|
| sources | 1 | ING-01 | stable/core | cap.sources | CP,PG,PA,E2E-002 | — |
| source_guide | 1 | ING-01 | stable/core | cap.source_guide | CP,PG,PA | — |
| source_pdf | 1 | ING-01 | stable/core | cap.source_pdf | CP,PG,PA,E2E-002 | — |
| source_plain_text_and_pasted_text | 1 | ING-01 | stable/core | cap.source_plain_text_and_pasted_text | CP,PG,PA,E2E-002 | — |
| custom_providers | 1 | MOD-01 | stable/core | cap.custom_providers | CP,PG,PA | — |
| grounded_chat | 1 | RAG-01 | stable/core | cap.grounded_chat | CP,PG,PA,E2E-001 | — |
| chat_configuration | 1 | RAG-01 | stable/core | cap.chat_configuration | CP,PG,PA | — |
| chat_lifecycle | 1 | RAG-01 | stable/core | cap.chat_lifecycle | CP,PG,PA | — |
| citations | 1 | RAG-01 | stable/core | cap.citations | CP,PG,PA,E2E-001 | — |
| notebook_instructions | 1 | RAG-01 | stable/core | cap.notebook_instructions | CP,PG,PA | — |
| notebook_overview | 1 | RAG-01 | stable/core | cap.notebook_overview | CP,PG,PA | — |
| notebook_management | 1 | UI-01 | stable/core | cap.notebook_management | CP,PG,PA | — |
| output_language | 1 | UI-01 | stable/core | cap.output_language | CP,PG,PA | — |
| appearance | 1 | UI-01 | stable/core | cap.appearance | CP,PG,PA | — |
| responsive_web_access | 1 | UI-01 | stable/core | cap.responsive_web_access | CP,PG,PA | MAN-004, MAN-005 |
| source_organization | 2 | ING-02 | stable/core | cap.source_organization | CP,PG,PA | — |
| source_markdown | 2 | ING-02 | stable/core | cap.source_markdown | CP,PG,PA,E2E-002 | — |
| source_docx | 2 | ING-02 | stable/core | cap.source_docx | CP,PG,PA,E2E-002 | — |
| source_pptx | 2 | ING-02 | stable/core | cap.source_pptx | CP,PG,PA,E2E-002 | — |
| source_csv | 2 | ING-02 | stable/core | cap.source_csv | CP,PG,PA,E2E-002 | — |
| source_spreadsheet_files_formats | 2 | ING-02 | stable/core | cap.source_spreadsheet_files_formats | CP,PG,PA,E2E-002 | — |
| source_images | 2 | ING-02 | stable/core | cap.source_images | CP,PG,PA,E2E-002 | — |
| source_audio | 2 | ING-02 | stable/core | cap.source_audio | CP,PG,PA,E2E-002 | — |
| source_epub_files | 2 | ING-02 | stable/core | cap.source_epub_files | CP,PG,PA,E2E-002 | — |
| source_optional_authenticated_restricted_repositories_through_generic_connectors | 2 | ING-02 | late/optional | cap.source_optional_authenticated_restricted_repositories_through_generic_connectors | CP,PG,E2E-002 | — |
| source_web_urls | 2 | ING-02 | stable/core | cap.source_web_urls | CP,PG,PA,E2E-002 | — |
| source_public_youtube_urls_transcript_backed_video_sources | 2 | ING-02 | stable/core | cap.source_public_youtube_urls_transcript_backed_video_sources | CP,PG,PA,E2E-002 | — |
| source_optional_cloud_document_storage_connectors_implemented_through_generic_adapters | 2 | ING-02 | late/optional | cap.source_optional_cloud_document_storage_connectors_implemented_through_adapters | CP,PG,E2E-002 | — |
| code_data_analysis | 3 | EXE-01 | stable/core | cap.code_data_analysis | CP,PG,PA,E2E-008 | — |
| agentic_chat | 3 | RSR-01 | stable/core | cap.agentic_chat | CP,PG,PA,E2E-008 | — |
| source_discovery | 3 | RSR-01 | stable/core | cap.source_discovery | CP,PG,PA,E2E-008 | — |
| deep_research | 3 | RSR-01 | stable/core | cap.deep_research | CP,PG,PA,E2E-008 | — |
| artifact_lifecycle | 4 | STD-01 | stable/core | cap.artifact_lifecycle | CP,PG,PA,E2E-003 | — |
| notes | 4 | STD-02 | stable/core | cap.notes | CP,PG,PA,E2E-004 | — |
| reports | 4 | STD-02 | stable/core | cap.reports | CP,PG,PA | MAN-003 |
| interactive_learning_overview | 4 | STD-02 | stable/core | cap.interactive_learning_overview | CP,PG,PA | — |
| data_tables | 4 | STD-02 | stable/core | cap.data_tables | CP,PG,PA | — |
| mind_maps | 4 | STD-02 | stable/core | cap.mind_maps | CP,PG,PA | — |
| flashcards | 4 | STD-02 | stable/core | cap.flashcards | CP,PG,PA | — |
| quizzes | 4 | STD-02 | stable/core | cap.quizzes | CP,PG,PA | — |
| slide_decks | 5 | STD-03 | stable/core | cap.slide_decks | CP,PG,PA | MAN-003 |
| infographics | 5 | STD-03 | stable/core | cap.infographics | CP,PG,PA | MAN-003 |
| audio_overview | 6 | MED-01 | stable/core | cap.audio_overview | CP,PG,PA,E2E-013 | MAN-002 |
| interactive_audio_overview | 6 | MED-01 | advanced/provider-dependent | cap.interactive_audio_overview | CP,PG | MAN-002 |
| video_overview | 6 | MED-01 | stable/core | cap.video_overview | CP,PG,PA,E2E-013 | MAN-003, MAN-010 |
| cinematic_video | 6 | MED-01 | advanced/provider-dependent | cap.cinematic_video | CP,PG,E2E-013 | MAN-003, MAN-010 |
| private_sharing | 7 | COL-01 | stable/core | cap.private_sharing | CP,PG,PA,E2E-005 | — |
| public_notebooks | 7 | COL-01 | late/optional | cap.public_notebooks | CP,PG | — |
| notebook_copying | 7 | COL-01 | stable/core | cap.notebook_copying | CP,PG,PA,E2E-005 | — |
| featured_published_notebooks | 7 | COL-01 | late/optional | cap.featured_published_notebooks | CP,PG | — |
| usage_analytics | 7 | COL-01 | late/optional | cap.usage_analytics | CP,PG | — |
| restricted_connector_sources | 7 | ING-02 | late/optional | cap.restricted_connector_sources | CP,PG | — |
| realtime_notebook_voice_chat | 7 | MED-01 | provisional/announced | cap.realtime_notebook_voice_chat | CP,PG | MAN-009 |
| recorded_audio_capture | 7 | MED-01 | provisional/announced | cap.recorded_audio_capture | CP,PG | MAN-009 |
| starter_artifacts | 7 | STD-01 | late/optional | cap.starter_artifacts | CP,PG | — |
| evolving_note_integration | 7 | STD-02 | provisional/announced | cap.evolving_note_integration | CP,PG | — |
| editable_study_aids_and_performance_follow_up | 7 | STD-02 | provisional/announced | cap.editable_study_aids_and_performance_follow_up | CP,PG | — |
| native_mobile_client | null | SCOPE-GUARD | deliberate-non-target | null | CP | — |
| pwa_offline_client | null | SCOPE-GUARD | deliberate-non-target | null | CP | — |
| google_account_coupling | null | SCOPE-GUARD | deliberate-non-target | null | CP | — |
| third_party_plugin_marketplace | null | SCOPE-GUARD | deliberate-non-target | null | CP | — |

## TABLE C — verification-group inventory

test_path prefixes (count = requirements covered):
tests/meta/release_contract/ 52; tests/security/ 51; tests/performance/ 47; tests/meta/normative_extraction/ 41; tests/security/authorization/ 33; tests/contracts/providers/ 29; tests/faults/jobs/ 27; tests/deploy/rootless/ 22; tests/domain/invariants/ 21; tests/ingestion/golden/ 20; tests/e2e/grounding/ 18; tests/security/bubblewrap/ 18; tests/e2e/media/ 16; tests/e2e/studio/ 15; tests/e2e/research/ 13; tests/indexing/ 11; tests/e2e/web/ 11; tests/provenance/golden/ 10; tests/evaluation/ 9; tests/meta/capabilities/ 9; tests/meta/phase_gates/ 6; tests/architecture/dependencies/ 4; tests/architecture/composition/ 4; tests/contracts/adapters/ 4; docs/evidence/ (.md, ARCH-23) 4; null 12.

evidence_path prefixes: artifacts/verification/ = 495; null = 12.

## TABLE D — anomalies (plan must record as spec decisions)

1. 12 narrative requirements (ARCH-00-001..012) carry no test_path/evidence_path/VER IDs, tier=none — intentional for narratives.
2. ARCH-05-001 (ch05 domain-model) → deployment component (other 19 ch05 records → domain_model).
3. ARCH-14-001 (ch14 media-realtime) → studio_artifacts component (other 15 → media_generation).
4. No duplicate VER IDs: 495 unique, 1:1 with non-narrative requirements.
5. No capability has empty required_test_groups (all 61 include CAP-PROFILE-001).
6. Registry has 23 distinct implementation_component values (not 24).

## CHECKSUMS
TABLE A total = 507 (58+52+51+47+33+29+27+23+20+20+18+18+16+15+13+12+11+11+10+9+6+4+4). TABLE B rows = 61 (phases 15/13/4/8/2/4/11 + 4 null). Tiers: PR 155, nightly 166, RC 170, review 4, none 12.
