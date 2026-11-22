# AeroDoc v0.1 demo

Allow 2–3 minutes after setup. Build the image, prepare the corpus and
initialize or reuse the ledger ahead of time using the [Docker guide](docker.md).
Run the commands from the repository root in PowerShell.

## 0:00–0:35 · Start and check the service

```powershell
docker compose --env-file .env.example up -d --no-build
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expect `{"status":"ok","retrieval":"bm25"}`. If startup is still in
progress, retry the health check after a few seconds. Open
`http://127.0.0.1:8000/docs` to show the request schema. The health check
and Swagger page do not send an answer request.

## 0:35–2:15 · Walk through the recorded outputs

The four examples below replay the recorded BM25 k=5 and GPT-6 Luna test
run `20261122T094126Z-3ecd1ad3`. Questions are from the
[frozen dataset](../eval/test_questions.json). Answer text and statuses
are transcribed from the archived HTTP responses. See the
[evaluation summary](test_evaluation_summary.md) for review status.

### T01 · Cited body-text answer

**Question.** Why might a technician with a smaller build work more efficiently with a different set of tools?

**Recorded status.** `answered`

> A technician with a smaller build may work more efficiently when tools and equipment are tailored to their size, because one size does not fit everyone. [S1]

**Source.** [S1] points to the Anthropometry passage on PDF page 627,
printed page 14-4. The cited chunk is body text.

### T05 · Answer from figure text

**Question.** The sample job card in Figure 14-35 marks the task as a duplicate inspection. How many people does it say are needed to do the work and inspect it?

**Recorded status.** `answered`

> Two people: one to perform the task and one to inspect it. [S1]

**Source.** [S1] points to Figure 14-35 on PDF page 653, printed page 14-30.
The sample card directly supports the two-person requirement. The
specific division of duties is a reasonable inference in the
`assistant_review`. Human review remains pending.

### T19 · Abstention on a missing detail

**Question.** What revision identifier appears on the MEDA results form described in the chapter?

**Recorded status.** `insufficient_evidence`, with `answer: null` and
`sources: []`.

**Context.** The dataset's absence check inspected PDF pages 633–634,
printed pages 14-10–14-11. Those passages describe MEDA and what the form
records. The revision identifier is absent from the chapter. The response
returned no cited page or figure.

### T14 · Retrieval failure despite a page hit

**Question.** Why is feeling alert an unreliable way to rule out fatigue during maintenance?

**Recorded status.** `insufficient_evidence`, with `answer: null` and
`sources: []`.

**Expected evidence.** PDF page 639, printed page 14-16, explains that a
fatigued person may still feel wide awake and engaged. BM25 retrieved
chunks associated with that page, but the necessary sentence was absent
from the first five chunks. The response returned no cited page or figure.

## 2:15–2:45 · Stop the service

```powershell
docker compose --env-file .env.example stop
```

The stop command preserves the mounted data and SQLite ledger.

## Optional live question

For a separate live run, follow the [runtime key instructions](docker.md#başlatma-loglar-ve-durdurma)
and send one request while the service is running. On a cache miss this can
make a paid OpenAI call, and outputs can differ from the recorded demo.

```powershell
$body = @{
    question = 'Why might a technician with a smaller build work more efficiently with a different set of tools?'
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/ask -Method Post -ContentType 'application/json' -Body $body
```
