# Fuzzing-ADK-Agent-via-GitLab-pipeline

## ⚡ TL;DR

* This project **extends** the base repo [ADK-Agent-on-Google-Cloud-with-GitLab-pipeline](https://github.com/ferranverdes/ADK-Agent-on-Google-Cloud-with-GitLab-pipeline).  
* It **reuses the same build and deploy pipeline**, infrastructure layout, and ADK agent/Ollama setup from the base project.  
* The only addition is a **`fuzz` stage in `.gitlab-ci.yml`** that uses **FuzzyAI** to fuzz the deployed agent for prompt-injection and related issues plus **OpenAI `gpt-4o`** for response classification.  
* You only need to configure the **extra variables required for FuzzyAI + OpenAI**, primarily `OPENAI_API_KEY` as a GitLab CI/CD variable.

This README focuses solely on the **fuzzing stage configuration**. For all details about **build, deploy, Pulumi, and GCP setup**, refer to the upstream project's README.

## 🧩 Project Context

This repository assumes you have already followed, or will follow, the instructions from the upstream project:

* Base repo: [ADK-Agent-on-Google-Cloud-with-GitLab-pipeline](https://github.com/ferranverdes/ADK-Agent-on-Google-Cloud-with-GitLab-pipeline).  
* That project explains how to:
  * Build and deploy a **GPU-backed Ollama backend** (`mistral:7b`) on Google Cloud Run.  
  * Build and deploy a **Google ADK agent** (Ona) in front of that backend.  
  * Wire **Pulumi (Python)** and **GitLab CI** to perform `build` and `deploy` stages.

In this repo, we **do not duplicate** those explanations. Instead, we keep the same layout:

* `ollama-backend/`, `adk-agent/`, and `environments/` behave exactly as in the base project.  
* `.gitlab-ci.yml` inherits the **`build`** and **`deploy`** stages from the base project and adds one more: **`fuzz`**.  

The **fuzz stage** runs after the application is deployed and uses **FuzzyAI** to send adversarial prompts to the deployed agent, classifying responses with **OpenAI `gpt-4o`**.

## 🔍 Fuzzing Components

### FuzzyAI configuration (`fuzzyai/config.json`)

The FuzzyAI config file in this repo looks like:

```json
{
  "model": "rest/http.raw",
  "extra": [
    "scheme=https",
    "response_jsonpath=$.response"
  ],
  "classifier": "oai",
  "classifier_model": "openai/gpt-4o",
  "attack_modes": ["def", "pls", "dan"],
  "target-prompts-file": "adversarial_prompts.list"
}
```

Key points:

* **`model: "rest/http.raw"`** – FuzzyAI talks directly to the deployed agent via HTTP.  
* **`extra`** – Configures HTTPS and where to find the model's response in the JSON payload (e.g. `$.response`).  
* **`classifier: "oai"` + `classifier_model: "openai/gpt-4o"`** – FuzzyAI uses OpenAI GPT‑4o as a classifier to judge responses.  
* **`attack_modes`** – Predefined attack styles such as defensive (`def`), prompt-leak (`pls`), and jailbreak (`dan`).  
* **`target-prompts-file`** – List of adversarial prompts to run against your agent.

FuzzyAI reads the OpenAI API key from the standard environment variable **`OPENAI_API_KEY`**, which we will configure in GitLab CI.

## 🧪 GitLab CI Pipeline (`.gitlab-ci.yml`)

The pipeline in this repo has **three stages**:

* `build` – same as the base project (builds container images with Pulumi + Docker-in-Docker).  
* `deploy` – same as the base project (deploys Ollama backend + ADK agent to Cloud Run).  
* `fuzz` – **new** stage defined in this repo, which runs after `deploy`.

We only cover the **`fuzz`** stage here; see the upstream README for `build` and `deploy` details.

### Fuzz stage job

The `fuzz` stage job in `.gitlab-ci.yml` is `fuzzyai_jailbreak_scan` and looks like:

```yaml
fuzzyai_jailbreak_scan:
  stage: fuzz
  image: python:3.12
  needs:
    - job: deploy
  variables:
    FUZZYAI_TARGET_URL: "$OLLAMA_BACKEND_URL"
    FUZZYAI_HTTP_METHOD: "POST"
  before_script:
    - cd fuzzyai
    - pip install git+https://github.com/cyberark/FuzzyAI.git@8184b96
  script:
    - fuzzyai fuzz -C config.json -e host="$(echo "$OLLAMA_BACKEND_URL" | sed -E 's|https?://||')"
    - python scripts/fuzzyai_to_gitlab_dast.py results/*/report.json gl-dast-report.json
  artifacts:
    when: always
    paths:
      - fuzzyai/gl-dast-report.json
    reports:
      dast: fuzzyai/gl-dast-report.json
```

How it works:

* **`needs: [deploy]`** – ensures fuzzing only runs after your Cloud Run services are deployed and `OLLAMA_BACKEND_URL` is available.  
* **Image `python:3.12`** – provides a clean Python environment.  
* **`before_script`** – installs FuzzyAI from GitHub inside the `fuzzyai/` directory.  
* **`variables`** – sets:
  * `FUZZYAI_TARGET_URL` to the deployed backend (`$OLLAMA_BACKEND_URL`).  
  * `FUZZYAI_HTTP_METHOD` to `POST`.  
* **`script`** – runs `fuzzyai fuzz` with:
  * `-C config.json` – points to the FuzzyAI config shown above.  
  * `-e host=...` – passes the deployed backend host, derived from `OLLAMA_BACKEND_URL`.  
* **GitLab DAST report** – after the scan, the job converts the latest `results/*/report.json` into `fuzzyai/gl-dast-report.json`, uploaded as a GitLab **DAST** report (`artifacts:reports:dast`). This makes findings show up in GitLab's Security Dashboard.

At runtime, FuzzyAI will:

1. Use `OPENAI_API_KEY` from the environment to talk to OpenAI.  
2. Send adversarial prompts defined in `adversarial_prompts.list` to the deployed agent.  
3. Classify responses using `openai/gpt-4o`.  

## 🔐 Required GitLab CI/CD Variables

In addition to the variables required by the base project (i.e., `PULUMI_ACCESS_TOKEN`, `GOOGLE_CREDENTIALS_B64`), this repo requires one **extra** variable for fuzzing:

### 1️⃣ `OPENAI_API_KEY`

This key is used by FuzzyAI to call the OpenAI API.

1. Obtain an **OpenAI API key** from your [OpenAI account](https://platform.openai.com/api-keys).  
2. In your GitLab project, go to **Settings → CI/CD → Variables**.  
3. Add a new variable:
   * **Key:** `OPENAI_API_KEY`  
   * **Value:** your generated OpenAI API key  
   * **Environment:** "All (default)" 
   * **Visibility:** ✅ **Masked**  
   * **Protection:** 🚫 **Unprotected** (for demonstration purposes in this example)  

FuzzyAI will automatically read `OPENAI_API_KEY` from the environment when the `fuzz` job runs.

> ⚠️ **Important:** In a real production setup, you would typically **protect** this variable and restrict where it can be used. Leaving it unprotected is only recommended here for demo and experimentation.

## ▶️ Running the Pipeline

Once you have:

1. Followed the **build/deploy** setup from the upstream project (Pulumi config, GCP project, service account, etc.).  
2. Configured all required GitLab CI/CD variables, including **`OPENAI_API_KEY`**.  

You can trigger the full pipeline by:

* Pushing a commit to the default branch (e.g. `main`) in your GitLab fork, or  
* Manually triggering the pipeline from **CI/CD → Pipelines → Run pipeline**.

The stages will execute in order:

1. **`build`** – builds images with Pulumi (see upstream README).  
2. **`deploy`** – deploys Cloud Run services and exports `OLLAMA_BACKEND_URL` + `AGENT_URL`.  
3. **`fuzz`** – runs FuzzyAI against the deployed backend using `openai/gpt-4o` for response classification.

After the fuzz stage completes, you can inspect the job logs to see which prompts were executed and how the target responded. More importantly, because the job uploads a GitLab **DAST** report (`fuzzyai/gl-dast-report.json`), successful jailbreaks are surfaced as first-class security findings in GitLab.

To review the results in the GitLab UI, open your project and go to **Secure → Vulnerability Report**. You should see new findings created from the fuzz run, typically one per prompt/response pair that the classifier considered a policy break or jailbreak:

![Vulnerability Report Dashboard](https://gitlab.com/ferran.verdes/static/-/raw/main/images/fuzzing-adk-agent-via-gitlab-pipeline-vulnerability-report.png)

Clicking a finding opens the details view, where you can review the representative evidence captured by the scan (what was sent, what was returned, and why it was flagged):

![Issue Found](https://gitlab.com/ferran.verdes/static/-/raw/main/images/fuzzing-adk-agent-via-gitlab-pipeline-specific-vulnerability.png)


## 🎯 Learning Objectives

This project demonstrates how to:

* Extend an existing **GitLab + Pulumi + GCP** deployment with an automated **fuzzing stage**.  
* Use **FuzzyAI** to fuzz a deployed LLM-backed agent over HTTP.  
* Integrate **OpenAI `gpt-4o`** as a classifier inside CI, using `OPENAI_API_KEY` as a masked GitLab CI/CD variable.  
* Keep core deployment logic in a base project, while layering **security testing** as an extra pipeline stage.
