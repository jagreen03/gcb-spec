# ADR-001: Cascade ADC reset at stage boundaries

## Status
Accepted

## Context
Prior optical compute proposals hit a precision wall from accumulated analog
noise across cascade stages.

## Decision
Reset the analog noise floor at each stage boundary.

## Consequences
Converts a physics constraint into an engineering parameter (headroom bits
reserved in the 12-bit ADC). Determines FP4/INT4 packing factors.

