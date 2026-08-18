# Provenance Guard — Planning

## 1. System Overview

Provenance Guard is a Flask backend that analyzes text submissions and estimates whether they are likely AI-generated or human-written.

A submission enters through `POST /submit`. The system runs two independent detection signals: an LLM-based signal and a stylometric heuristic signal. Their scores are combined into one confidence score, which is mapped to an attribution category and transparency label.

Every classification is written to a structured audit log. Creators can contest a classification through `POST /appeal`, which changes the content status to `under_review` and records the creator's reasoning.

The system intentionally communicates uncertainty because automated AI detection cannot prove authorship.

## 2. Detection Signals

### Signal 1 — LLM Classification

The first signal uses a Groq-hosted language model.

It returns an AI-likelihood score from 0 to 1.

- 0 = strongly human-like
- 1 = strongly AI-like

It considers semantic and stylistic characteristics such as formulaic wording, predictable phrasing, repetitive structures, and overly polished transitions.

Its limitation is that an LLM can make attribution mistakes, especially on formal, edited, or unusual writing.

### Signal 2 — Stylometric Heuristics

The second signal uses pure Python statistics.

It measures:

- sentence-length variation
- vocabulary diversity
- punctuation/structural patterns

These properties provide a structurally different signal from the LLM.

Its limitation is that human writing can naturally be very uniform or formal, while AI text can be deliberately edited to appear irregular.

## 3. Confidence Scoring

The two scores are combined as:

```text
confidence =
    0.65 * llm_score
    + 0.35 * stylometric_score
```

The final score ranges from 0 to 1.

The thresholds are:

0.00 <= confidence <= 0.30: likely human-written
0.30 < confidence < 0.70: uncertain
0.70 <= confidence <= 1.00: likely AI-generated

A score in the middle range represents genuine uncertainty rather than forcing a binary classification. The thresholds provide a conservative buffer around the middle of the score range so that borderline results are classified as uncertain.

## 4. Transparency Labels

The system returns one of three plain-language labels.

### Likely AI-generated:

Our analysis found stronger signals associated with AI-generated text. This result is an estimate, not proof of authorship."

### Likely human-written

Our analysis found stronger signals associated with human-written text. This result is an estimate, not proof of authorship.

### Uncertain attribution:

The signals were mixed or not strong enough to make a confident determination. This result is an estimate, not proof of authorship."

The labels intentionally communicate that the classifier provides an estimate rather than proof of authorship.

## 5. Appeals Workflow

A creator can submit an appeal using:

POST /appeal

Required fields:

content_id
creator_reasoning

The system:

Finds the original classification.
Changes its status to under_review.
Stores the creator's reasoning.
Creates a separate structured audit-log entry.
Returns confirmation.

Automated reclassification is not required.

## 6. API Surface

POST /submit

Accepts:

{
"text": "content",
"creator_id": "creator-123"
}

Returns:

content ID
attribution
confidence
transparency label
POST /appeal

Accepts:

{
"content_id": "id",
"creator_reasoning": "reason"
}

Returns the appeal status.

GET /log

Returns structured audit-log entries.

## 7. Rate Limiting

The submission endpoint uses Flask-Limiter.

Configured limits:

10 submissions per minute
100 submissions per day

This allows normal creator usage while preventing a client from flooding the service with requests.

Exceeding the limit returns HTTP 429.

## 8. Audit Logging

Each classification records:

timestamp
content ID
creator ID
attribution
confidence
LLM score
stylometric score
status

Appeals additionally record:

appeal timestamp
appeal reasoning
original classification
original confidence
under_review status

The audit log is stored as structured JSON.

## 9. Error Handling

The API handles:

missing JSON
missing text
missing creator ID
very short text
detection failures
nonexistent content IDs for appeals
missing appeal reasoning
rate-limit violations

## 10. Edge Cases

Short text

Very short text provides too little information for meaningful stylometric analysis. The API therefore requires a minimum amount of text.

Formal human writing

Formal writing may have uniform sentence structures and vocabulary, causing the system to overestimate AI likelihood.

Edited AI writing

AI-generated text that has been heavily edited by a human may become less detectable.

Human writing with repetitive style

A human writer may naturally use repetitive or predictable structures, which can increase the stylometric AI score.

## 11. False Positive Strategy

False positives are especially important because an incorrect AI label can harm a creator.

The system reduces this risk by:

Using two different signals.
Providing an uncertain classification.
Showing confidence rather than only a binary result.
Providing an appeals workflow.

The system treats the result as an estimate rather than proof.

## 12. Architecture

    +----------------+
    | Client |
    +-------+--------+
    |
    | POST /submit
    v
    +----------------+
    | Flask API |
    +-------+--------+
    |
    +-----------+-----------+
    | |
    v v
    +----------------+ +--------------------+
    | LLM Detection | | Stylometric Signal |
    | Signal | | |
    +-------+--------+ +---------+----------+
    | |
    | LLM score | Style score
    +------------+------------+
    |
    v
    +----------------+
    | Confidence |
    | Scoring |
    +-------+--------+
    |
    v
    +----------------+
    | Transparency |
    | Label |
    +-------+--------+
    |
    v
    +----------------+
    | Audit Log |
    +-------+--------+
    |
    v
    +----------------+
    | JSON Response |
    +----------------+

Appeal Flow:

Client
|
| POST /appeal
| content_id + reasoning
v
Flask API
|
v
Find original decision
|
v
status = under_review
|
v
Audit Log
|
v
Confirmation

### Submission Flow

`POST /submit` receives the raw text and creator ID. The LLM signal produces an `llm_score`, while the stylometric signal produces a `stylometric_score`. The confidence scorer combines these scores into a single confidence value, which determines the attribution category and transparency label. The classification and signal scores are then written to the audit log before the structured response is returned to the client.

### Appeal Flow

`POST /appeal` receives a `content_id` and creator reasoning. The system finds the original classification, changes its status to `under_review`, records the appeal reasoning and original decision in the audit log, and returns confirmation to the creator.

## 13. State Management

The content_id uniquely identifies each submission.

The audit log acts as persistent state for:

original classification
confidence
individual signal scores
creator ID
status
appeals

The content ID connects an appeal to the original classification.

## 14. Testing Plan

I tested the system using:

Clearly AI-like formal writing.
Casual human-like writing.
Formal borderline writing.
Lightly edited AI-like writing.

I also tested:

/submit
/log
/appeal
nonexistent content IDs
missing fields
rate limiting

## 15. AI Tool Plan

### Milestone 3 — Submission Endpoint + First Signal

I provided ChatGPT with my detection-signal specification and architecture diagram and asked it to generate a Flask application skeleton with a `POST /submit` endpoint and an LLM-based detection function.

The generated code provided the initial Flask route structure and Groq API integration. I reviewed and modified the implementation before using it, including input validation, content ID generation, and structured audit logging.

I verified the first signal independently with several test texts before connecting it to the endpoint.

### Milestone 4 — Second Signal + Confidence Scoring

I provided ChatGPT with the detection-signal specification, uncertainty design, and architecture diagram and asked it to implement the stylometric signal and combine the two signals into a confidence score.

I specifically verified the generated weighting against my specification. The final implementation uses:

`0.65 * llm_score + 0.35 * stylometric_score`

I also tested the attribution thresholds using actual scores. The final implementation classifies scores of 0.70 or higher as likely AI-generated, scores of 0.30 or lower as likely human-written, and scores between those thresholds as uncertain.

### Milestone 5 — Production Layer

I used ChatGPT to help implement the transparency-label function, appeals workflow, audit logging, and Flask-Limiter configuration.

I reviewed the generated label text and ensured the final strings matched the labels documented in this specification. I also verified that appeals change the content status to `under_review` and that the appeal reasoning is recorded.

For rate limiting, I used `10 per minute;100 per day` with in-memory Flask-Limiter storage for local development and verified that excessive requests return HTTP 429.

## 16. Implementation Decisions

The project instructions referenced a specific Groq model, but model availability can change.

During development I checked the models available through my Groq account and used an available model instead.

The detection code keeps the model name in one location so it can be changed without redesigning the rest of the application.
