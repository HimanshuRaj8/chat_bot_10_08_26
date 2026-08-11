# Claim Period Intelligence - Discussion Notes

## Background

The requisition report contains fields such as:

- Created On
- Approved On
- Document Title
- Requisition Description/Details

A challenge identified in the current system is that many reimbursement requests contain the actual claim period (month, duration, date range, etc.) only within the free-text description field.

Examples:

- "May Month Parking Reimbursement"
- "Parking Charges March 2026"
- "Internet bill reimbursement for April 2026"
- "18th Feb 26 to 3rd Apr 26 Parking Bill"
- "Parking Bills Apr+May2026"
- "Wifi Apr - Jun 3 months"

The period information is not stored in a structured column.

---

# Business Problem

## Employee Perspective

Employees should be able to:

- Identify the last period for which they raised a claim.
- Check whether they have already submitted a claim for a specific month.
- Detect missing months or durations.
- Avoid accidental duplicate submissions.
- View their reimbursement timeline.

Example:

### Question

"What period did I last claim internet reimbursement for?"

### Expected Response

Latest Internet Claim:

- Period: Jul-2025 to Feb-2026
- Applied On: DD-MM-YYYY
- Status: Approved

---

## Finance Perspective

Finance teams should be able to:

- Detect duplicate reimbursement requests.
- Detect overlapping claim periods.
- Review employee reimbursement timelines.
- Identify missing claim periods.
- Perform audit and compliance checks.

Example:

Employee has submitted:

- Parking Claim: March 2026
- Parking Claim: March 2026

Potential duplicate detected.

---

# Observation From Sample Data

The requisition data includes several period patterns.

## Single Month Pattern

Examples:

- May Month Parking Reimbursement
- Parking Charges March 2026
- Internet bill reimbursement for April 2026
- Driver Salary - June

Extracted Period:

- Mar-2026
- Apr-2026
- May-2026
- Jun-2026

---

## Date Range Pattern

Examples:

- 18th Feb 26 to 3rd Apr 26 Parking Bill
- Parking 1 Apr to 5 Jun 48 days
- Reimbursement for Japan travel from 26 April 2026 to 2 May 2026

Extracted Period:

- 18-Feb-2026 → 03-Apr-2026
- 01-Apr-2026 → 05-Jun-2026
- 26-Apr-2026 → 02-May-2026

---

## Multi-Month Pattern

Examples:

- Internet re-imbursement from Jul25 till Feb 26
- Parking Bills Apr+May2026
- Newspaper and Periodicals Apr - Jun
- Wifi Apr - Jun 3 months

Extracted Period:

- Jul-2025 → Feb-2026
- Apr-2026 → May-2026
- Apr-2026 → Jun-2026
- Apr-2026 → Jun-2026

---

## Unknown Pattern

Examples:

- Car Parking Bill
- Parking Slips
- Internet Charges
- Parking Fee Reimbursement

In such cases:

- Period may not be determinable.
- System can fall back to Created On month.
- Confidence level should be marked LOW.

---

# Recommended Solution

## Core Concept

Create a new derived business attribute called:

### Claim Period Intelligence

Instead of only relying on requisition descriptions.

---

# Backend Changes

## 1. Create Claim Period Extractor

New utility:

```text
backend_v3/utils/claim_period_extractor.py
```

Functions:

```python
extract_period()

extract_single_month()

extract_date_range()

extract_multi_month()

normalize_period()
```

---

## 2. Generate Additional Fields

For every requisition record create:

```python
claim_period_start
claim_period_end
claim_period_text
period_confidence
```

Example:

```python
{
    "claim_period_start": "2026-03-01",
    "claim_period_end": "2026-03-31",
    "claim_period_text": "Mar-2026",
    "period_confidence": "HIGH"
}
```

---

## 3. Enhance Data Loading Pipeline

Current:

```text
Excel Dataset
    ↓
Repository
    ↓
Analytics
```

Proposed:

```text
Excel Dataset
    ↓
Claim Period Extractor
    ↓
Enriched Dataset
    ↓
Repository
    ↓
Analytics
```

---

## 4. Update Repository Layer

Store:

```python
df["claim_period_start"]
df["claim_period_end"]
df["claim_period_text"]
df["period_confidence"]
```

as normal dataframe columns.

---

## 5. Add Analytics Service

New module:

```text
backend_v3/services/claim_period_analytics.py
```

Possible methods:

```python
get_last_claimed_period()

get_claim_timeline()

find_missing_periods()

find_duplicate_periods()

find_overlapping_periods()
```

---

## 6. Recommended Additional Field

Instead of only storing a date range, also generate:

```python
claim_months
```

Example:

```python
[
    "2026-04",
    "2026-05",
    "2026-06"
]
```

for:

```text
Wifi Apr - Jun 3 months
```

Benefits:

- Easier duplicate detection
- Easier monthly analytics
- Simpler reporting logic

---

# Employee Insights

## Last Claimed Period

Query:

```text
What period did I last claim for?
```

Response:

```text
Latest Claim Period:
May 2026
```

---

## Claim Timeline

Query:

```text
Show my internet reimbursement timeline.
```

Response:

```text
Mar-2026
Apr-2026
May-2026
Jun-2026
Jul-2026
```

---

## Missing Month Detection

Example:

```text
Feb-2026 ✓
Mar-2026 ✓
Apr-2026 ✓
May-2026 ✗
Jun-2026 ✓
```

Potential Missing Month:

```text
May-2026
```

---

## Already Claimed Check

Query:

```text
Have I already claimed March internet reimbursement?
```

Response:

```text
Yes.

Req ID: REQ-1234
Claim Period: March 2026
Status: Approved
```

---

# Finance Insights

## Duplicate Detection

Query:

```text
Show duplicate parking reimbursements.
```

Result:

```text
Employee: John Doe

Req-101
March-2026

Req-145
March-2026

Potential Duplicate Found
```

---

## Overlapping Duration Detection

Example:

```text
Claim 1:
01-Mar-2026 → 31-Mar-2026

Claim 2:
20-Mar-2026 → 10-Apr-2026
```

Output:

```text
Overlap:
20-Mar-2026 → 31-Mar-2026
```

---

## Missing Claim Analysis

Example:

```text
Driver Salary

Jan ✓
Feb ✓
Mar ✓
Apr ✓
May ✗
Jun ✓
```

Output:

```text
Missing Month:
May-2026
```

---

## Finance Dashboard

Potential widgets:

```text
Duplicate Claims : 12

Overlapping Claims : 5

Employees Missing Periods : 21
```

---

# Frontend Changes

## Option 1 (Recommended Initially)

No UI changes.

Keep everything in chat.

Examples:

```text
What was my last claimed period?

Have I already claimed April parking reimbursement?

Show my claim timeline.
```

---

## Option 2

Enhance existing tables.

Current:

| Req ID | Description | Status |
|---------|------------|---------|

Proposed:

| Req ID | Description | Claim Period | Status |
|---------|------------|--------------|---------|

---

## Option 3

Finance Dashboard

Additional cards:

- Duplicate Claims
- Overlapping Claims
- Missing Claim Periods
- Audit Alerts

---

# Suggested Implementation Roadmap

## Sprint 1

Backend Foundation

- Build Claim Period Extractor
- Generate claim_period_start
- Generate claim_period_end
- Generate claim_period_text
- Generate confidence score

Deliverable:

```text
What was my last claimed period?
```

---

## Sprint 2

Advanced Analytics

- Duplicate period detection
- Missing period detection
- Claim timeline generation
- Self-verification queries

---

## Sprint 3

Finance Dashboard

- Duplicate alerts
- Overlap detection
- Compliance reports
- Period audit dashboard

---

# Executive Summary

The proposal is to introduce a new analytics capability called:

## Claim Period Intelligence

This feature automatically derives reimbursement periods from requisition descriptions and enables:

### Employees

- Last claimed period lookup
- Missing month detection
- Claim history timeline
- Duplicate prevention

### Finance Teams

- Duplicate reimbursement detection
- Overlapping period detection
- Audit support
- Compliance tracking

Recommendation:

Focus first on robust claim period extraction. Once claim periods become structured fields, all employee and finance insights become significantly easier to implement.