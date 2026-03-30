# Resume-Deduplicator-and-Webhook-Service

# Assignment 1: AI/ML — Resume Deduplication System

## Objective

Detect duplicate resumes in a large database (~1 lakh resumes), even when explicit identifiers like email or phone number differ.

## Approach

The system uses a **3-stage pipeline** to balance speed and accuracy:

### Stage 1 — Exact Identifier Match
Fast O(1) check on normalized email and phone number. If any identifier matches exactly, it is immediately flagged as a duplicate (score = 1.0).

### Stage 2 — MinHash LSH (Approximate Nearest Neighbour)
Uses **MinHash + Locality Sensitive Hashing (LSH)** to find candidate matches in sub-linear time. This is critical for scalability to 1 lakh+ resumes — instead of comparing every pair (O(n²)), LSH reduces the candidate set to a small cluster of likely matches.

- Character 3-shingles are extracted from the normalized full text.
- A 128-permutation MinHash signature is computed per resume.
- An LSH index (threshold = 0.5 Jaccard) returns candidate IDs in milliseconds.

### Stage 3 — TF-IDF Cosine Similarity
For each LSH candidate, a **weighted cosine similarity** score is computed across 4 resume sections:

| Section    | Weight |
|------------|--------|
| Skills     | 35%    |
| Experience | 35%    |
| Education  | 15%    |
| Summary    | 15%    |

If the weighted score exceeds the configurable threshold (default **0.85**), the resume is declared a duplicate.

---

## Architecture

```
resume_dedup/
├── src/
│   ├── deduplicator.py   ← Core engine (MinHash, LSH, TF-IDF)
│   └── main.py           ← CLI entry-point
├── data/
│   ├── sample_resumes.json   ← Corpus for demo/testing
│   └── query_resume.json     ← Sample query resume
├── tests/
│   └── test_deduplicator.py  ← Pytest test suite
├── requirements.txt
```

---

## Setup & Run

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the built-in demo

```bash
cd src
python main.py demo
```

This runs 3 test cases with synthetic resumes and prints similarity scores.

### 3. Build index from a corpus

```bash
python main.py build --corpus ../data/sample_resumes.json --model ../model.pkl
```

### 4. Check if a resume is a duplicate

```bash
python main.py check --model ../model.pkl --resume ../data/query_resume.json
```

### 5. Run tests

```bash
cd ..
pytest tests/ -v
```

---

## Sample Test Cases & Results

### Test 1: Duplicate — same phone, different email, updated content

| Field       | Query Resume              | Stored Resume             |
|-------------|---------------------------|---------------------------|
| Name        | John Doe                  | John Doe                  |
| Email       | johndoe.new@gmail.com     | john.doe@email.com        |
| Phone       | +91-9876543210            | +91-9876543210 ✅ MATCH   |
| Skills      | Python, Django, FastAPI…  | Python, Django, REST…     |

**Result:** ✅ IS DUPLICATE — Method: `exact_phone`

---

### Test 2: Not a duplicate — completely different person

| Field    | Query Resume              |
|----------|---------------------------|
| Name     | Carlos Rivera             |
| Role     | HR Manager                |
| Skills   | Recruitment, HRMS…        |

**Result:** ❌ NOT DUPLICATE — Score: ~0.05

---

### Test 3: Exact copy of an existing resume

**Result:** ✅ IS DUPLICATE — Score: 1.0, Method: `tfidf_cosine`

---

## Design Decisions

- **Why MinHash LSH?** Enables sub-linear search over 1 lakh resumes. Direct TF-IDF comparison over all pairs would require ~5 billion comparisons.
- **Why section-level scoring?** Candidates often change their email/title but keep skills and education. Weighting sections captures this nuance.
- **Why not use an LLM directly?** LLMs are expensive at 1 lakh scale. The pipeline uses LLM-style semantic understanding (TF-IDF n-grams) with classical speed.

---

## LLM Usage Disclosure

Claude (claude.ai) was used during the development of this project for:

1. **Architecture design** — Prompts asked for approaches to near-duplicate detection at scale, comparing MinHash, SimHash, and embedding-based methods.
2. **Code generation** — Core `deduplicator.py` structure was drafted with AI assistance and then reviewed and refined.
3. **Test case design** — Claude helped identify edge cases (same phone / different email, minor content updates, etc.).

> Chat link/prompts used: [https://claude.ai/chat/8bad0d43-7a26-461a-8a56-9c8044ea7908](https://claude.ai/share/46fff1e5-a949-4a15-8806-e478b4d8f8e7)

# Assignment 2: Backend — Django Webhook Service

## Objective

A Django application that receives, validates, stores, and processes webhook events from external systems.

---

## Features

- `POST /webhook/receive/` — Accept and process webhook payloads
- `GET  /webhook/events/`  — List stored events (filter by `event_type`)
- `GET  /webhook/events/<id>/` — Retrieve a single event
- HMAC-SHA256 signature verification
- Event-type dispatch (user.created, payment.success, payment.failed, order.placed)
- Full Django Admin support
- Celery-ready background task structure

---

## Architecture

```
webhook_service/
├── manage.py
├── requirements.txt
├── webhook_service/
│   ├── settings.py     ← Django configuration
│   ├── urls.py         ← Root URL routing
│   └── wsgi.py
└── webhooks/
    ├── models.py       ← WebhookEvent model
    ├── views.py        ← API views (receive, list, detail)
    ├── serializers.py  ← DRF serializers
    ├── tasks.py        ← Processing logic / Celery-ready
    ├── urls.py         ← App URL patterns
    └── tests.py        ← Test suite
```

---

## Setup Instructions

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Apply migrations

```bash
cd webhook_service
python manage.py migrate
```

### 3. Create superuser (optional, for Admin)

```bash
python manage.py createsuperuser
```

### 4. Run development server

```bash
python manage.py runserver
```

Server runs at: `http://127.0.0.1:8000`

### 5. Run tests

```bash
python manage.py test webhooks
```

---

## Environment Variables

| Variable            | Default                          | Description                      |
|---------------------|----------------------------------|----------------------------------|
| `DJANGO_SECRET_KEY` | (insecure dev key)               | Django secret key                |
| `WEBHOOK_SECRET`    | `my-super-secret-webhook-key`    | HMAC secret for signature check  |
| `DEBUG`             | `True`                           | Debug mode                       |
| `ALLOWED_HOSTS`     | `localhost,127.0.0.1`            | Comma-separated allowed hosts    |

---

## API Documentation

### POST /webhook/receive/

Receive a webhook event.

**Headers:**
```
Content-Type: application/json
X-Webhook-Signature: sha256=<hmac_sha256_of_body>
```

**Request body:**
```json
{
  "event_type": "user.created",
  "data": {
    "user_id": "u123",
    "email": "alice@example.com",
    "name": "Alice"
  }
}
```

**Success Response (200):**
```json
{
  "message": "Webhook received successfully.",
  "event_id": 1,
  "status": "processed"
}
```

**Error Responses:**
- `400 Bad Request` — missing `event_type` or invalid JSON
- `403 Forbidden` — invalid or missing signature

---

### GET /webhook/events/

List all webhook events (most recent 100).

**Optional query param:** `?event_type=user.created`

**Response (200):**
```json
[
  {
    "id": 1,
    "event_type": "user.created",
    "payload": { "event_type": "user.created", "data": { "email": "a@b.com" } },
    "source_ip": "127.0.0.1",
    "status": "processed",
    "error_message": "",
    "received_at": "2024-01-15T10:30:00Z",
    "processed_at": "2024-01-15T10:30:00Z"
  }
]
```

---

### GET /webhook/events/<id>/

Retrieve a single event by ID.

**Response (200):** Same structure as list item.
**Response (404):** `{ "error": "Event not found." }`

---

## Sample Request / Response Examples

### Sending a webhook with curl

```bash
# Generate signature
SECRET="my-super-secret-webhook-key"
PAYLOAD='{"event_type":"payment.success","data":{"order_id":"ORD-789","amount":1499}}'
SIG=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print "sha256="$2}')

curl -X POST http://127.0.0.1:8000/webhook/receive/ \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$PAYLOAD"
```

**Response:**
```json
{
  "message": "Webhook received successfully.",
  "event_id": 3,
  "status": "processed"
}
```

### Listing events

```bash
curl http://127.0.0.1:8000/webhook/events/
curl "http://127.0.0.1:8000/webhook/events/?event_type=payment.success"
```

### Retrieving a specific event

```bash
curl http://127.0.0.1:8000/webhook/events/3/
```

---

## Supported Event Types

| Event Type        | Handler Action                              |
|-------------------|---------------------------------------------|
| `user.created`    | Logs new user email and name                |
| `payment.success` | Logs order ID and amount                    |
| `payment.failed`  | Logs order ID and failure reason (warning)  |
| `order.placed`    | Logs order ID and item count                |
| *(any other)*     | Logged as unknown event type                |

---

## Celery Integration (Bonus)

To switch to async background processing:

1. Install Celery and Redis:
   ```bash
   pip install celery redis
   ```

2. In `tasks.py`, uncomment `@shared_task`

3. In `views.py`, replace:
   ```python
   process_webhook_event(event)
   ```
   with:
   ```python
   process_webhook_event.delay(event.id)
   ```

4. Run a Celery worker:
   ```bash
   celery -A webhook_service worker --loglevel=info
   ```

---

## LLM Usage Disclosure

Claude (claude.ai) was used during development of this project for:

1. **Architecture decisions** — Prompts explored Django REST Framework patterns, HMAC signature verification, and Celery integration strategies.
2. **Code scaffolding** — Views, models, and serializers were initially generated with AI assistance and then reviewed.
3. **Test case generation** — Claude helped identify security edge cases (missing signature, tampered body, etc.).

> Chat link/prompts used: [(https://claude.ai/share/46fff1e5-a949-4a15-8806-e478b4d8f8e7)](https://claude.ai/share/46fff1e5-a949-4a15-8806-e478b4d8f8e7)
