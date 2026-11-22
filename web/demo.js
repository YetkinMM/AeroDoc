"use strict";

const form = document.querySelector("#ask-form");
const question = document.querySelector("#question");
const submit = document.querySelector("#live-submit");
const buttons = Array.from(document.querySelectorAll("[data-example]"));
const results = document.querySelector("#results");
const mode = document.querySelector("#mode");
const state = document.querySelector("#answer-state");
const statusLabel = document.querySelector("#status-label");
const answerText = document.querySelector("#answer-text");
const provenance = document.querySelector("#provenance");
const sources = document.querySelector("#sources");
let archive;

function renderSources(entries) {
  sources.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "empty-source";
    empty.textContent = "No sources cited.";
    sources.append(empty);
    return;
  }

  for (const entry of entries) {
    const card = document.createElement("article");
    card.className = "source-card";
    const heading = document.createElement("h3");
    const citation = document.createElement("span");
    citation.className = "citation";
    citation.textContent = entry.label ? `[${entry.label}]` : "";
    heading.append(citation, document.createTextNode("FAA AMT General Handbook"));
    card.append(heading);

    const facts = document.createElement("dl");
    const fields = [
      ["PDF page", entry.pdf_pages],
      ["Printed page", entry.printed_pages],
      ["Figure", entry.figure_id ? [entry.figure_id] : []],
    ];
    for (const [label, values] of fields) {
      if (!Array.isArray(values) || !values.length) continue;
      const group = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      term.textContent = values.length > 1 ? `${label}s` : label;
      detail.textContent = values.join(", ");
      group.append(term, detail);
      facts.append(group);
    }
    card.append(facts);
    sources.append(card);
  }
}

function render({ label, message, kind, recorded = false, sourceList = [] }) {
  mode.hidden = false;
  mode.textContent = recorded ? "Recorded example — not a live request" : "Live request";
  provenance.hidden = !recorded;
  provenance.textContent = recorded ? `Frozen test run ${archive.run_id}` : "";
  state.dataset.kind = kind;
  statusLabel.textContent = label;
  answerText.textContent = message;
  renderSources(sourceList);
}

function showAnswer(payload, recorded) {
  if (payload.status === "answered" && typeof payload.answer === "string") {
    render({ label: "Answered", message: payload.answer, kind: "success", recorded,
      sourceList: Array.isArray(payload.sources) ? payload.sources : [] });
  } else if (payload.status === "insufficient_evidence") {
    render({ label: "Insufficient evidence", kind: "notice", recorded,
      message: "The retrieved passages did not provide enough evidence to answer this question." });
  } else if (payload.status === "budget_exceeded") {
    render({ label: "Budget limit reached", kind: "error",
      message: "The local budget did not allow a provider call." });
  } else {
    render({ label: "Service error", kind: "error",
      message: "AeroDoc could not complete the live request." });
  }
}

function selectExample(button) {
  const example = archive.examples[button.dataset.example];
  question.value = example.question;
  for (const choice of buttons) choice.setAttribute("aria-pressed", String(choice === button));
  showAnswer(example, true);
}

for (const button of buttons) {
  button.disabled = true;
  button.addEventListener("click", () => selectExample(button));
}
question.addEventListener("input", () => {
  question.setCustomValidity("");
  for (const button of buttons) button.setAttribute("aria-pressed", "false");
});

fetch("/assets/examples.json")
  .then((response) => {
    if (!response.ok) throw new Error("Examples unavailable");
    return response.json();
  })
  .then((data) => {
    archive = data;
    for (const button of buttons) button.disabled = submit.disabled;
    if (!question.value && !submit.disabled && document.activeElement !== question) {
      selectExample(buttons.find((button) => button.dataset.example === "T05"));
    }
  })
  .catch(() => {
    if (!submit.disabled && mode.hidden) {
      state.dataset.kind = "error";
      statusLabel.textContent = "Recorded examples unavailable";
    }
  });

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (submit.disabled) return;
  const value = question.value.trim();
  if (!value) {
    question.setCustomValidity("Enter a question.");
    question.reportValidity();
    return;
  }

  submit.disabled = true;
  question.readOnly = true;
  for (const button of buttons) {
    button.disabled = true;
    button.setAttribute("aria-pressed", "false");
  }
  results.setAttribute("aria-busy", "true");
  render({ label: "Loading", message: "Searching the handbook and preparing a response…", kind: "loading" });
  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: value }),
    });
    showAnswer(await response.json(), false);
  } catch {
    showAnswer({}, false);
  } finally {
    results.removeAttribute("aria-busy");
    question.readOnly = false;
    submit.disabled = false;
    for (const button of buttons) button.disabled = !archive;
  }
});
