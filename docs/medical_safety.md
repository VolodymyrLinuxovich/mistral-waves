# Medical safety guardrails

Version 0.1.0 (2026-07-23). Owner: risk-communication lead. Requires documented
review before demo (Day 12).

## Framing
This app is **evidence-informed heat-risk safety support, not a diagnosis** and
not a medical device. The following disclaimer is shown prominently on every
personal-result screen (uk + en), sourced from `config/recommendation_rules.yaml`:

> This is an environmental heat-risk estimate and safety guidance. It is not a
> medical diagnosis and does not replace a healthcare professional.

## Hard rules (encoded in config/risk_rules.yaml + recommendation_rules.yaml)

The app **never** advises a user to:
- stop or change medication or dosage;
- ignore a prescribed fluid restriction;
- use a universal water quantity regardless of health condition;
- remain home despite emergency symptoms.

### Fluid-restricted users (heart failure / CKD / prescribed restriction)
No fixed hydration volume is ever given. The user is told to follow their
clinician's fluid plan and to discuss a heat-day plan with their clinician
(`REC-FLUID-RESTRICTED`). This rule overrides any generic hydration advice.

### Medication
Output states that some medicines affect hydration/blood pressure/thermoregulation,
that the user must not stop or alter medication without professional advice, and
to ask a clinician or pharmacist about a heat-day plan (`REC-MEDICATION`).

### Emergency red flags — override ALL scoring
Confusion, loss of consciousness, seizure, inability to drink, severe weakness,
very hot skin with altered mental state, rapid deterioration, severe shortness of
breath, chest pain, stroke-like symptoms → **force CRITICAL** and direct the user
to emergency medical assistance via **103**. Protective factors can never reduce
this. An app notification is explicitly stated to be insufficient as emergency care.

## No fake precision
The engine outputs a category (low/moderate/high/critical) + confidence label +
explanation. It never outputs a probability such as "73% hospitalization risk".

## Privacy
No names, medical-record numbers, or detailed diagnoses are collected. Profile is
stored locally by default; no account required for the demo. No patient-level or
personally identifiable medical data are stored server-side.
