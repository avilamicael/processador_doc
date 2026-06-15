# Feature Research

**Domain:** Intelligent Document Processing (IDP) / Document organization automation — fiscal documents BR (NF-e, boletos), single-tenant app
**Researched:** 2026-06-15
**Confidence:** MEDIUM-HIGH (IDP patterns well-documented across Klippa, Docsumo, Rossum, Unstract, Nanonets, Parseur, Google Document AI; BR fiscal specifics HIGH from deterministic standards; competitor file-automation specifics LOW where vendors don't publish)

## How the Core Mechanisms Work in Real Products

Before categorizing, here is how the four mechanisms the downstream consumer asked about are typically designed. These shape the dependency map.

### 1. Template builder — two competing designs
- **Zonal / anchor-based (legacy):** user draws bounding boxes on a sample document; fields map to coordinates or to text anchors. High precision on fixed layouts, brittle across emitter variation. Requires a doc viewer + box-drawing UI (HIGH complexity). Products: ABBYY, older Kofax.
- **Schema-first / template-free (modern, LLM era):** user declares the *fields they want* (name, type, hint) — not their position. The LLM extracts layout-agnostically against a JSON Schema. Position no longer matters; emitter variation handled by the model. Products: Unstract, Docsumo "no manual setup", LlamaIndex, Rossum.
- **Verdict for this project:** schema-first is correct. PROJECT.md already commits to JSON Schema output + Pydantic-style validation, and OpenAI structured outputs make this native. The "template" = (document type label + ordered field list + per-field type/validation + automation rules). "Sub-template per emitter" = a specialization that overrides field hints/automations for a specific CNPJ. This avoids building a coordinate-drawing UI entirely. **The template builder is a form editor, not a canvas editor.** That is a major complexity reduction worth defending.

### 2. Automatic classification — "which template does this doc match?"
Two layers, used together in real products:
- **Deterministic pre-classification (free, exact):** detect NF-e by 44-digit access key / DANFE barcode; detect boleto by 47/48-digit linha digitável + barcode (Code 128 / FEBRABAN). This routes ~the majority of fiscal docs to the right type at zero AI cost and 100% precision. This is a BR-specific differentiator.
- **AI classification (fallback):** for everything deterministic parsing can't label, send text/image to the LLM with the list of available templates and ask it to pick (or return "none" → quarantine). Sub-template (emitter) selection keys off extracted CNPJ/issuer name once the type is known.

### 3. Field extraction — hybrid routing (already in scope, validate the shape)
Standard production pattern: **native text → deterministic parse → LLM with schema → validate → confidence-gate.** PROJECT.md already nails this. The non-obvious production lesson (Alan/Medium): always validate LLM output against a typed schema, and on validation failure route to human review *with the structured error attached*, not just a generic "low confidence" flag.

### 4. Human review / correction — confidence-gated queue
Every serious IDP product (Docsumo, Klippa DocHorizon, Google Doc AI HITL, Unstract) has: a configurable **confidence threshold**, a **review queue**, a **side-by-side doc-image + editable-fields UI**, and corrections that feed forward. Industry claim: HITL pushes accuracy toward ~99%+. The threshold being **user-configurable** (speed vs. accuracy trade-off) is table stakes, not a differentiator. Model retraining-from-corrections is a differentiator most don't have; with an LLM, the cheap equivalent is *capturing corrections as few-shot examples / hint refinements per sub-template* rather than retraining.

### 5. Usage metering
For consumption billing the infrastructure lesson is: meter at **token granularity** with an **idempotency key per processed file** so retries/queue redelivery never double-count (and dedup-by-hash already supports this). Surface a real-time per-period usage view. Metering by *document* is wrong for this product because context-processing tokens vary — PROJECT.md already decided tokens, which matches industry guidance for AI-cost-pass-through.

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these and a buyer evaluating against Klippa/Docsumo/local fiscal tools feels the product is incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Multi-format ingest (PDF + images) | Source docs are scanned and native mixed | LOW | In scope |
| OCR / text extraction with fallback to AI on scans | Native-text-only tools fail on photographed docs | MEDIUM | In scope (hybrid routing) |
| Automatic document-type classification | Core promise; manual sorting defeats the purpose | MEDIUM | In scope; lean on deterministic pre-class for fiscal |
| Field extraction to structured output (JSON/CSV) | Extracted data must leave the tool usable | MEDIUM | In scope (JSON Schema) |
| Field validation (CNPJ, date, value, access-key checksum) | Fiscal data wrong = downstream errors; users expect format guarantees | LOW-MEDIUM | In scope; add checksum validation for access key + linha digitável |
| Confidence scoring per field/doc | Users won't trust a black box on fiscal data | MEDIUM | Drives the review gate; needs a defined confidence model per extraction path |
| Human review/correction queue (low-confidence routing) | Universal IDP expectation; the trust mechanism | HIGH | In scope; side-by-side viewer is the costly part |
| Configurable confidence threshold | Speed-vs-accuracy control is standard | LOW | Don't hardcode; expose per-template ideally |
| Rename + move automation driven by extracted fields | This IS the product's organize promise | MEDIUM | In scope; needs a token/template string mini-language |
| Dry-run / preview before applying | Users will not let software touch their files blind | MEDIUM | In scope; non-negotiable given file mutation |
| Audit log + undo | Reversibility for file operations; fiscal/LGPD traceability | HIGH | In scope; undo is what makes move/rename safe |
| Quarantine for unmatched/failed docs | "Never lose a file" — files must never silently vanish | LOW-MEDIUM | In scope |
| Dedup by hash | Avoid reprocessing/recharging same file | LOW | In scope; doubles as metering idempotency key |
| Batch processing of a folder | Volume is the reason to buy | MEDIUM | In scope (CLI/folder) |
| Template/field configuration UI by the customer | Buyer must adapt to their own doc set without vendor | HIGH | In scope; schema-first form editor (not canvas) |
| Usage visibility (tokens/calls per period) | Customer pays by consumption; must see what they spend | MEDIUM | In scope; needs accurate, idempotent metering |

### Differentiators (Competitive Advantage)

Aligned with Core Value ("classified, named, organized — automatically and *reliably*, without losing files or blindly trusting AI"). Differentiation is on **trust + BR-fiscal precision + cost control**, not on having-more-models.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Deterministic BR-fiscal parsing before AI (NF-e key / XML, boleto linha digitável + barcode) | 100% accurate, zero token cost on the most common docs; generic IDP tools treat these as "just another document" | MEDIUM | Strong moat vs. foreign IDP; checksum-verifiable |
| Cost-minimizing extraction routing (native text → deterministic → AI only on the remainder) | Directly lowers the customer's bill under consumption pricing — a selling point, not just an optimization | MEDIUM | Already the architecture; market it explicitly |
| Per-emitter sub-templates with own rules/automations | Real fiscal flows differ per supplier; lets a power user encode "Fornecedor X → this folder pattern" | MEDIUM | In scope; specialization layer over base template |
| Hot-folder auto-processing (drop files, they organize themselves) | "Set and forget" — closest thing to magic for the target user | MEDIUM | In scope |
| Configurable page-splitting (N pages per doc) | Multi-doc PDFs/scan batches are common; competitors often force fixed splitting | MEDIUM | In scope |
| Single-tenant / runs on customer's own machine | LGPD-friendly: fiscal data stays local except explicit OpenAI calls; no SaaS data-residency objection | MEDIUM | Already the model; lead with this for privacy-sensitive buyers |
| Explainable "what was sent to OpenAI" view | LGPD; lets the customer trust/audit what leaves the machine | MEDIUM | Noted as evolution goal in PROJECT.md; high trust value |
| Corrections feed forward as per-sub-template hints/few-shot | Cheap LLM-era substitute for model retraining; accuracy improves without ML pipeline | MEDIUM-HIGH | Differentiator most SMB tools lack |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Canvas/zonal box-drawing template editor | "Looks powerful," familiar from ABBYY-era tools | Brittle to emitter layout variation; massive UI build; redundant with LLM layout-agnostic extraction | Schema-first form editor (declare fields, not positions) |
| Multi-tenant / accounts / SaaS login | Seems like the obvious "real product" shape | Explicitly out of scope; adds auth, isolation, residency burden; contradicts single-tenant local model | One instance per customer; isolation by deployment |
| Model fine-tuning / training your own model | "AI should learn from us" | Cost, MLOps, data-labeling burden; OpenAI structured output + few-shot covers 95% | Capture corrections as per-sub-template hints/few-shot examples |
| Automations beyond rename/move in v1 (email, WhatsApp, API push, ERP sync) | Customers always want "and then send it to..." | Each integration is a maintenance + auth surface; dilutes v1 reliability focus | Ship rename/move solid; add an extensible action interface later |
| Embedded billing/invoicing in the app | "Charge me automatically" | Out of scope; billing done externally from metered usage; payment compliance burden | Export accurate usage data; bill outside the app |
| Auto-apply automations on every doc with no review by default | "Full automation, no clicks" | On fiscal files this risks misfiled/renamed-wrong records and erodes trust; one bad move = lost customer | Dry-run default + confidence gate; auto-apply only above a high, user-set threshold |
| Real-time live processing / streaming everywhere | "Instant" feels modern | Adds complexity; OpenAI rate limits + batches make async-queue the right model | Async queue with retry (in scope); show progress, not real-time |
| Unlimited custom field types / formulas / scripting in templates v1 | Power users ask for it | Turns the template builder into a programming environment; testing burden | Fixed validated types (string/date/value/CNPJ/key) + a simple rename token language |
| OCR for arbitrary handwriting / low-quality photos as a guarantee | "It should read anything" | Sets accuracy expectations the model can't meet; generates support load | Confidence gate + quarantine; be explicit about supported quality |

## Feature Dependencies

```
Ingest (folder/upload/CLI)
    └──requires──> Dedup by hash ──also-feeds──> Usage metering (idempotency key)
            └──requires──> Page splitting (configurable)
                    └──requires──> Extraction routing
                            ├── Native PDF text extract
                            ├── Deterministic fiscal parse (NF-e key/XML, boleto linha digitável)
                            └── AI extraction (OpenAI, JSON Schema)
                                    └──requires──> Field validation (CNPJ/date/value/checksum)
                                            └──produces──> Confidence score
                                                    └──gates──> Human review queue
                                                            └──requires──> Side-by-side doc viewer + editable fields

Templates (schema-first field list + validations)
    └──enables──> Automatic classification ──requires──> deterministic pre-class + AI fallback
            └──enables──> Sub-templates (per emitter, keyed on CNPJ)
                    └──carries──> Automation rules (rename/move)
                            └──requires──> Dry-run / preview
                                    └──requires──> Audit log + Undo
                                            └──backstopped-by──> Quarantine

Async queue with retry ──underlies──> all extraction + automation steps
Human review corrections ──enhances──> Sub-template hints/few-shot (differentiator)
```

### Dependency Notes

- **Rename/move requires Dry-run + Audit/Undo + Quarantine:** these four are one trust system. Shipping automation without the safety trio violates Core Value and the integrity constraint. They belong in the same phase, automation last.
- **Classification requires Templates first:** you can't classify against templates that don't exist. Template builder must precede classification, which precedes sub-templates.
- **Human review gates on Confidence, which depends on the extraction path:** deterministic parses are inherently high-confidence (checksum-verified); AI parses need a defined confidence model. The confidence model must be designed before the review gate is meaningful.
- **Dedup-by-hash doubles as the metering idempotency key:** build once, use for both no-double-process and no-double-charge.
- **Sub-templates enhance classification but conflict with "fully automatic, no setup":** the more emitter-specific rules, the more configuration the user owns. Frame sub-templates as opt-in power, not required.
- **Corrections→hints enhancement requires the review queue first:** can't capture corrections without a correction UI.

## MVP Definition

### Launch With (v1) — matches PROJECT.md Active scope

- [ ] Ingest: hot folder + manual upload + CLI batch — the three entry points; volume is the value
- [ ] PDF + image input — table stakes
- [ ] Configurable page splitting — common multi-doc reality
- [ ] Dedup by hash — prevents reprocess/recharge; metering idempotency
- [ ] Hybrid extraction: native text → deterministic fiscal parse → OpenAI w/ JSON Schema — cost + accuracy core
- [ ] Deterministic NF-e (key/XML) + boleto (linha digitável/barcode) parsing — BR differentiator, zero-cost precision
- [ ] Field validation (CNPJ, date, value, access-key/linha-digitável checksum) — fiscal correctness
- [ ] Schema-first template builder (field list + types + validations) — customer self-service, no canvas
- [ ] Sub-templates per emitter — real fiscal differentiation
- [ ] Automatic classification (deterministic + AI fallback, "none" → quarantine) — core promise
- [ ] Confidence scoring + configurable threshold — trust mechanism
- [ ] Human review queue with side-by-side viewer + editable fields — the trust UI
- [ ] Rename + move automation with field-token strings — the organize promise
- [ ] Dry-run / preview — non-negotiable before file mutation
- [ ] Audit log + undo — reversibility
- [ ] Quarantine — never lose a file
- [ ] Async queue with retry — handles batches + OpenAI rate limits
- [ ] Usage metering by tokens/calls with idempotency — consumption billing support

### Add After Validation (v1.x)

- [ ] Corrections → per-sub-template hints/few-shot — trigger: users repeatedly correcting the same emitter
- [ ] Explainable "what was sent to OpenAI" view — trigger: LGPD scrutiny / privacy-sensitive buyer asks
- [ ] Per-template (not just global) confidence thresholds — trigger: users want stricter rules on some doc types
- [ ] Richer rename token language (slugify, date reformat, conditionals) — trigger: real folder-naming needs exceed simple substitution
- [ ] Structured export to CSV/Excel beyond JSON — trigger: accounting users want spreadsheet handoff

### Future Consideration (v2+)

- [ ] Additional automation actions (email, WhatsApp, API/ERP push) — explicitly out of v1 scope; defer until rename/move proven
- [ ] Desktop packaging (Tauri) — defer until "install and open" demand appears
- [ ] Alternative AI providers / on-prem model — defer; OpenAI decided for v1
- [ ] NFS-e and other fiscal doc types' deterministic parsers — defer until demand beyond NF-e/boleto

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Hybrid extraction routing | HIGH | MEDIUM | P1 |
| Deterministic NF-e/boleto parsing | HIGH | MEDIUM | P1 |
| Schema-first template builder | HIGH | HIGH | P1 |
| Automatic classification | HIGH | MEDIUM | P1 |
| Human review queue + viewer | HIGH | HIGH | P1 |
| Rename/move automation | HIGH | MEDIUM | P1 |
| Dry-run + Audit/Undo + Quarantine | HIGH | HIGH | P1 |
| Dedup by hash | MEDIUM | LOW | P1 |
| Async queue with retry | HIGH | MEDIUM | P1 |
| Usage metering (tokens, idempotent) | HIGH | MEDIUM | P1 |
| Sub-templates per emitter | MEDIUM | MEDIUM | P1-P2 |
| Configurable confidence threshold | MEDIUM | LOW | P1 |
| Corrections → hints/few-shot | MEDIUM | MEDIUM-HIGH | P2 |
| Explainable "sent to OpenAI" view | MEDIUM | MEDIUM | P2 |
| Extra automation actions | MEDIUM | HIGH | P3 |
| Desktop packaging | LOW | MEDIUM | P3 |

## Competitor Feature Analysis

| Feature | Klippa DocHorizon / Docsumo / Rossum | Local BR fiscal tools (Consultar Danfe, ERPs) | Our Approach |
|---------|--------------------------------------|-----------------------------------------------|--------------|
| Classification | ML/LLM, layout-agnostic, no rigid templates | Barcode/key lookup only; little auto-classification | Deterministic-first + AI fallback (best of both) |
| Template/config | Schema or no-template setup; cloud SaaS | Fixed to fiscal types; no custom templates | Customer-built schema-first templates + emitter sub-templates |
| Human review | Built-in HITL queue, confidence threshold, corrections→retrain | Minimal/none | HITL queue + corrections→hints (no retraining cost) |
| File org automation | Focus on data export/AP workflow, not file rename/move | Storage/organization of notas | Rename/move as first-class, with dry-run + undo |
| Deployment | Cloud SaaS (data leaves premises) | Local/cloud mixed | Single-tenant, runs on customer machine (LGPD edge) |
| Billing | Per-page / per-doc / subscription | Subscription | Token-based consumption (reflects real AI cost) |
| Privacy/LGPD | Data to vendor cloud | Varies | Local-first; only explicit OpenAI calls leave machine |

**Net competitive position:** foreign IDP leaders are stronger on generic ML breadth and integrations; this product wins on (1) BR-fiscal deterministic precision at zero cost, (2) local/single-tenant LGPD posture, (3) file-organization automation as a first-class, reversible, trustworthy workflow rather than a data-export afterthought.

## Sources

- [Appian DocCenter IDP](https://appian.com/products/platform/process-automation/intelligent-document-processing-idp) — template/model builder, validation rules (MEDIUM)
- [Nutrient: What is IDP](https://www.nutrient.io/blog/what-is-intelligent-document-processing/) — classification/extraction/validation pipeline (MEDIUM)
- [Docsumo HITL](https://www.docsumo.com/platform/features/human-in-the-loop) — confidence-routed review (MEDIUM)
- [Unstract HITL](https://unstract.com/blog/human-in-the-loop-hitl-for-ai-document-processing/) and [no-template extraction](https://unstract.com/blog/ai-document-processing-no-manual-templates-custom-schema-support/) — schema-first, confidence thresholds (MEDIUM)
- [Klippa DocHorizon HITL](https://www.klippa.com/en/dochorizon/human-in-the-loop/) and [data extraction software roundup](https://www.klippa.com/en/blog/information/data-extraction-software/) — feature comparison (MEDIUM)
- [Parseur HITL best practices](https://parseur.com/blog/hitl-best-practices) — review workflow patterns (MEDIUM)
- [Turing IT Labs: Zonal OCR vs AI vs GPT](https://turingitlabs.com/data-extraction-software/) — template-builder design tradeoffs (MEDIUM)
- [Simon Willison: structured extraction with LLM schemas](https://simonw.substack.com/p/structured-data-extraction-from-unstructured) — schema-first validation (MEDIUM)
- [Alan engineering: LLM doc pipeline in production](https://medium.com/alan/lessons-from-running-an-llm-document-processing-pipeline-in-production-33d87f99cdb1) — validate-then-route-to-review lesson (MEDIUM)
- [TecnoSpeed: chave de acesso NF-e](https://blog.tecnospeed.com.br/chave-de-acesso/) and [Nonus leitor de chave NF-e](http://www.nonus.com.br/leitor-chave-acesso-nfe.php) — 44-digit key + Code128 barcode (HIGH)
- [Metronome usage-based billing](https://metronome.com/blog/usage-based-billing), [Lago metering](https://github.com/getlago/lago), [Schematic token-based billing](https://schematichq.com/pricing-resources/token-based-billing) — idempotent token metering (MEDIUM)

---
*Feature research for: IDP / fiscal-document organization automation (BR), single-tenant*
*Researched: 2026-06-15*
