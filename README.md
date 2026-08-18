# Provenance Guard

Provenance Guard is an AI-text attribution service that analyzes submitted text and estimates whether it is likely to be AI-generated, likely human-written, or uncertain.

The system combines an LLM-based signal with a lightweight stylometric signal and exposes the result through a Flask API. It also provides transparency labels, appeal handling, rate limiting, and a structured audit log.

> **Important:** This system provides an estimate rather than proof of authorship. AI-text detection is inherently uncertain, especially for edited AI output, formal human writing, short text, and text that has been heavily revised.

---

## Architecture Overview

A submission follows this path:

```text
Client
  |
  | POST /submit
  v
Flask API
  |
  v
Input validation
  |
  +----------------------+
  |                      |
  v                      v
LLM Signal         Stylometric Signal
  |                      |
  |                      |
  +----------+-----------+
             |
             v
      Confidence Score
             |
             v
     Attribution Decision
             |
       +-----+-----+
       |     |     |
       v     v     v
   Likely AI  Uncertain  Likely Human
             |
             v
      Transparency Label
             |
             v
        Audit Log

The main analysis function is analyze_text() in detector.py.

The two signals are:

LLM signal — asks an LLM to estimate the likelihood that the text was AI-generated.
Stylometric signal — analyzes structural properties of the writing such as sentence-length variation, vocabulary diversity, and punctuation.

The two signals are combined into one confidence score.

Detection Signals
1. LLM Signal

The LLM signal asks the language model to classify the submitted text and return an ai_score between 0 and 1.

0.0 = very unlikely to be AI-generated
1.0 = very likely to be AI-generated

This signal is useful because a language model can recognize linguistic patterns that are difficult to capture with simple statistical rules.

Why I chose it

An LLM can evaluate higher-level writing characteristics such as:

repetitive phrasing
generic wording
overly structured explanations
common AI-style transitions
predictable formal language
What it misses

The LLM can make mistakes because AI-generated text can be edited to sound human, while human writing can also be formal and structured.

For example, formal academic writing can sometimes look similar to AI-generated writing.

2. Stylometric Signal

The stylometric signal calculates several simple structural features.

It looks at:

sentence-length variance
vocabulary diversity
punctuation frequency

The implementation calculates a uniformity score based on sentence-length variance and combines it with unique-word ratio and punctuation frequency.

The result is normalized between 0 and 1.

Why I chose it

Stylometric analysis provides a second, independent signal instead of relying completely on the LLM.

It is also deterministic and inexpensive to calculate.

What it misses

Stylometric features are not proof of authorship.

For example:

short human text can look very uniform
formal human writing can have high vocabulary diversity
edited AI text can acquire human-like characteristics
different writing styles naturally produce different scores

Because of this, I use stylometrics as supporting evidence rather than treating it as a definitive classifier.

Confidence Scoring

The final confidence score combines the two AI-likelihood signals:

confidence = (
    0.60 * llm_score
    + 0.40 * stylometric_score
)

The LLM receives slightly more weight because it captures higher-level linguistic patterns, while the stylometric signal provides an independent structural signal.

The final value is clamped between 0 and 1.

The attribution thresholds are:

if confidence >= 0.70:
    attribution = "likely_ai"
elif confidence <= 0.30:
    attribution = "likely_human"
else:
    attribution = "uncertain"

This creates three possible outcomes:

Confidence	Attribution
>= 0.70	likely_ai
0.31 - 0.69	uncertain
<= 0.30	likely_human

I chose the uncertain range intentionally because the system should avoid presenting a weak classification as a fact.

Confidence Scoring Validation

I tested the detector using four different types of text.

High-confidence AI example

Text:

Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment.

Observed result:

LLM score:         0.75
Stylometric score: 0.6874
Confidence:        0.725
Result:            likely_ai

This is a high-confidence AI result because both signals contribute positively and the final score is above the 0.70 threshold.

High-confidence human example

Text:

ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably won't go back unless someone drags me there

Observed result:

LLM score:         0.10
Stylometric score: 0.5769
Confidence:        0.2908
Result:            likely_human

This result is below the 0.30 human threshold.

The informal language, conversational phrasing, and low LLM AI score contribute to the lower final score.

Uncertain example

I also tested formal human writing:

The relationship between monetary policy and asset price inflation has been extensively studied in the literature. Central banks face a fundamental tension between their mandate for price stability and the unintended consequences of prolonged low interest rates on equity and real estate valuations.

Observed result:

LLM score:         0.25
Stylometric score: 0.6418
Confidence:        0.4067
Result:            uncertain

This is an example of why an uncertain category is useful. The LLM signal is relatively low, but the stylometric signal is higher because the writing is formal and structured.

Transparency Labels

The system returns one of three transparency labels.

Likely AI-generated

Displayed when:

confidence >= 0.70

Exact label:

Likely AI-generated: Our analysis found stronger signals associated with AI-generated text. This result is an estimate, not proof of authorship.

Likely human-written

Displayed when:

confidence <= 0.30

Exact label:

Likely human-written: Our analysis found stronger signals associated with human-written text. This result is an estimate, not proof of authorship.

Uncertain attribution

Displayed when:

0.30 < confidence < 0.70

Exact label:

Uncertain attribution: The signals were mixed or not strong enough to make a confident determination. This result is an estimate, not proof of authorship.

The labels intentionally avoid claiming certainty about who actually authored the text.

Appeals

The system supports appeals when a creator disagrees with an attribution result.

An appeal includes:

content ID
creator ID
appeal reasoning
original attribution
original confidence
individual signal scores
timestamp
review status

For example, a creator can submit reasoning explaining that they created and edited the text themselves.

The appeal is recorded in the audit log with an under_review status.

This separates the automated classification from the human review process.

Rate Limiting

The /submit endpoint uses Flask-Limiter.

The configured limit is:

10 requests per minute
100 requests per day

The configuration uses in-memory storage for local development:

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)

The submit endpoint is protected with:

@limiter.limit("10 per minute;100 per day")
Why these limits?

A normal writer submitting their own work should not need to make more than a few submissions per minute. Ten submissions per minute provides enough room for normal experimentation and retries while preventing a script from continuously flooding the service.

The daily limit of 100 requests provides additional protection against sustained automated abuse.

For a production deployment, I would replace the in-memory storage with a shared persistent rate-limit store such as Redis so that limits work consistently across multiple application instances.

Rate-limit test

I tested the endpoint with 12 rapid requests:

for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "This is a test submission for rate limit testing purposes only.", "creator_id": "ratelimit-test"}'
done

Expected behavior:

200
200
200
200
200
200
200
200
200
200
429
429

The 429 responses demonstrate that the rate limit is being enforced after the allowed number of requests.

Audit Log

Every classification is recorded in a structured JSON audit log.

The log captures:

timestamp
content ID
creator ID
attribution
confidence
LLM score
stylometric score
status
appeal information when applicable

Example:

{
  "content_id": "948cb6d5-ff1c-4c36-866b-74f0de831879",
  "creator_id": "final-ai-test",
  "timestamp": "2026-08-18T19:31:06.249196+00:00",
  "attribution": "likely_ai",
  "confidence": 0.725,
  "llm_score": 0.75,
  "stylometric_score": 0.6874,
  "status": "classified"
}

Appeals are also recorded as structured events so there is a history of what happened to a submission.

I generated multiple classification entries and appeal events while testing the system.

API Usage
Submit text
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text":"Artificial intelligence represents a transformative paradigm shift in modern society.","creator_id":"test-user"}' | python -m json.tool

Example response:

{
    "attribution": "likely_ai",
    "confidence": 0.725,
    "content_id": "948cb6d5-ff1c-4c36-866b-74f0de831879",
    "label": "Likely AI-generated: Our analysis found stronger signals associated with AI-generated text. This result is an estimate, not proof of authorship."
}
Known Limitations

The detector should not be treated as proof of authorship.

One important limitation is formal human writing.

Academic, professional, and technical writing often uses:

structured sentences
consistent vocabulary
formal transitions
low conversational variation

These characteristics can increase the stylometric score even when the writing is completely human.

Another limitation is lightly edited AI text. If AI-generated text is substantially edited by a person, the LLM may assign it a low AI score even though AI was involved in creating the original draft.

Short texts are another difficult case because there are fewer linguistic features available for either signal.

Because of these limitations, the system intentionally includes an uncertain category instead of forcing every submission into AI or human.

Spec Reflection
How the specification helped

The specification provided a clear set of production requirements beyond simply building a classifier.

For example, the requirement for transparency labels encouraged me to avoid returning only a raw numerical score. The system now communicates whether the result is likely AI, likely human, or uncertain and explains that the result is only an estimate.

The requirements for appeals, rate limiting, and structured audit logs also helped shape the application into a more complete service rather than only a text-classification script.

Where my implementation diverged

The specification describes a simple combination of detection signals, but I adjusted the weighting during testing.

The final implementation uses:

0.60 * llm_score + 0.40 * stylometric_score

I chose this weighting because the LLM signal is more directly related to AI attribution, while the stylometric signal is better treated as supporting evidence.

I also kept a relatively wide uncertain range (0.30 to 0.70) because false certainty is a larger problem for an attribution system than acknowledging uncertainty.

AI Usage

I used AI assistance during development in several specific ways.

1. Detector design and debugging

I directed AI to help design a lightweight stylometric signal and combine it with an LLM-based classification signal.

The initial implementation used both signals, but I reviewed the weighting and changed it during testing rather than accepting the generated approach without modification.

I ultimately chose:

confidence = (
    0.60 * llm_score
    + 0.40 * stylometric_score
)
2. Test design

I used AI assistance to create test cases representing:

clearly AI-generated writing
clearly human conversational writing
formal human writing
lightly edited AI-style writing

I then ran these tests through my actual Flask API and used the observed results to adjust the scoring thresholds.

For example, the conversational human test produced:

confidence: 0.2908
result: likely_human

while the clearly AI-style test produced:

confidence: 0.725
result: likely_ai

This gave me evidence that the scoring system was producing meaningful variation.

3. Rate-limit implementation

I used AI assistance to understand and configure Flask-Limiter, including the required storage_uri="memory://" configuration for local development.

I then tested the implementation myself with repeated curl requests and verified that requests eventually returned HTTP 429.

Testing Summary

The final test set produced the following results:

Test	LLM	Stylometric	Confidence	Result
Clearly AI	0.75	0.6874	0.725	likely_ai
Clearly Human	0.10	0.5769	0.2908	likely_human
Formal Human	0.25	0.6418	0.4067	uncertain
Edited AI	0.00	0.7348	0.2939	likely_human

The results demonstrate meaningful variation between high-confidence AI, high-confidence human, and uncertain cases.

The edited-AI result also demonstrates a known limitation of the detector: edited AI text can be classified as human when the LLM signal is low.
```
