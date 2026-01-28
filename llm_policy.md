# Azure Blob Storage Cleanup Policy

**Version:** 1.0.0
**Last Updated:** 2026-01-28

## Purpose

This document defines the rules and guidelines for determining which blobs should be kept or deleted from Azure Blob Storage. The LLM uses this policy to make conservative, auditable decisions.

## Risk Level

**CONSERVATIVE**: When in doubt, mark for human review. Only make automatic decisions when completely certain.

---

## Positive Signals for DELETE

Blobs with these characteristics are candidates for deletion (but still require high confidence):

1. **Temporary/Cache Files**
   - Files with names containing: `tmp`, `temp`, `cache`, `.tmp`, `.cache`
   - Files in folders named: `temp/`, `tmp/`, `cache/`, `scratch/`
   
2. **Log Files (older than retention period)**
   - `.log` files older than 90 days
   - Debug logs, trace files
   
3. **Duplicate/Redundant Content**
   - Files with identical content hash but different names
   - Versioned files where newer version exists (e.g., `report_v1.pdf` when `report_v3.pdf` exists)
   
4. **Development/Test Artifacts**
   - Files clearly marked as test data
   - Development snapshots
   - Build artifacts (unless explicitly marked for retention)

5. **Empty or Near-Empty Files**
   - Files smaller than 100 bytes with no meaningful content
   - Files containing only whitespace

---

## Positive Signals for KEEP

Blobs with these characteristics should be preserved:

1. **Business-Critical Documents**
   - Financial records, invoices, receipts
   - Contracts, agreements, legal documents
   
2. **Customer Data**
   - User uploads
   - Customer-facing content
   - Personal information
   
3. **Recent Activity**
   - Files modified/accessed within last 30 days
   - Files with recent version tags
   
4. **Configuration and Code**
   - Configuration files
   - Source code
   - Deployment artifacts (production)
   
5. **Explicitly Labeled for Retention**
   - Files in folders containing: `keep`, `preserve`, `archive`, `backup`
   - Files with retention metadata

---

## NEVER DELETE (Strict Constraints)

**Automatic deletion is FORBIDDEN for:**

1. **Legal/Regulatory Requirements**
   - Files marked as legal holds
   - Compliance-related documents
   - Audit trails
   
2. **Personal Identifiable Information (PII)**
   - Unless explicitly authorized and documented
   - Requires human approval
   
3. **Active Production Data**
   - Files accessed in last 7 days
   - Files with active locks or leases
   
4. **Irreplaceable Content**
   - Original uploads without backups
   - Files marked as "master" or "source of truth"

---

## Edge Cases and Ambiguous Scenarios

When encountering these situations, ALWAYS route to human review:

1. **Mixed Signals**
   - File has both keep and delete indicators
   - Conflicting metadata
   
2. **Insufficient Context**
   - Cannot determine file purpose from name and preview
   - Missing key metadata
   
3. **Boundary Cases**
   - File age near retention cutoff
   - File size near threshold
   - Partial matches to rules
   
4. **Business Domain Uncertainty**
   - Unknown file types or formats
   - Unfamiliar naming conventions
   - Unclear organizational context

---

## Decision Workflow

1. Check NEVER DELETE constraints first → If match, route to human review
2. Look for clear KEEP signals → If found with high confidence, mark as keep
3. Look for clear DELETE signals → If found with high confidence and no keep signals, mark as delete
4. If mixed, ambiguous, or uncertain → Route to human review

---

## Confidence Requirements

- Automatic decisions require ≥95% confidence
- Self-consistency: 3-5 independent LLM calls must agree
- No violations of NEVER DELETE clauses
- Clear reasoning that can be audited

---

## Examples of Conservative Behavior

**Scenario 1:** File named "temp_report.pdf" but last modified yesterday
- **Decision:** HUMAN_REVIEW (mixed signals: temp name but recent activity)

**Scenario 2:** File named "invoice_2024_Q4.pdf" in "archive/" folder
- **Decision:** KEEP (business-critical, retention folder)

**Scenario 3:** File "debug.log" from 6 months ago, 50KB
- **Decision:** DELETE (if policy allows logs >90 days and confidence ≥0.95)

**Scenario 4:** File with encrypted content, unknown purpose
- **Decision:** HUMAN_REVIEW (insufficient context)
