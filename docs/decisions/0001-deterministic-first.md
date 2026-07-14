# ADR 0001: Deterministic-first, LLM-free Phase 1

## Status

Accepted for Phase 1.

## Context

Agent evaluation often mixes model nondeterminism, live APIs, and LLM-as-judge
scoring. That makes regressions hard to isolate: a failed run may reflect the
model, the judge, network drift, or the harness itself.

## Decision

Phase 1 of Agent Reliability Lab is **deterministic and LLM-free**:

- SQLite environment with deterministic seeds
- Typed tools and machine-checkable policies
- Rule-based graders (final state, tool calls, policy)
- A scripted reference agent that uses no LLM

No LLM providers, LangChain/LangGraph, or LLM judges in Phase 1.

## Consequences

**Positive:** Repeatable CI, clear failures, fast local feedback, trustworthy
harness before model variance is introduced.

**Negative:** Phase 1 does not measure natural-language agent quality; that
waits for later phases.

## Checkpoint note

As of Checkpoint 0, only packaging and documentation are implemented. The
deterministic runtime described above remains **planned** for Checkpoints 1–6.
