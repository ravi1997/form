# Form Analyser API

A powerful, customizable Python Flask analytics engine backed by MongoDB. Form Analyser parses and executes "Analysis Definitions" on top of raw form responses, allowing users to schedule background updates, evaluate multi-select arrays, compute Net Promoter Scores (NPS), generate funnels, and export comparative reports as PDFs or CSVs.

---

## Features

- **Dynamic Analysis Engine**: Processes numeric calculations, frequency analysis on categories/arrays, crosstabs, NPS calculations, funnel tracking, correlations, and time-series trends using MongoDB aggregation pipelines.
- **Auto-Schema Detection**: Samples existing data dynamically and autogenerates suggested analysis steps.
- **Secure Key-based Auth**: SHA-256 API key authentication (keys prefixed with `fa_`).
- **Cron Scheduling**: In-app background job scheduling using APScheduler.
- **Webhooks & Notifications**: Dispatches automated payloads on job success or failure.
- **Export Formats**: Seamlessly compiles reports into CSVs or PDF layouts with table rendering.

---

## Technology Stack

- **Framework**: Flask (Python)
- **Database**: MongoDB
- **Scheduling**: APScheduler
- **PDF Generation**: ReportLab
- **Containerization**: Docker & Docker Compose

---

## Directory Structure

```text
├── blueprints/             # API blueprints (Routes)
│   ├── auth_routes.py      # Keys creation & management
│   ├── analysis_routes.py  # Definition CRUD, runs, comparisons, exports
│   ├── form_routes.py      # Form schema metadata routes
│   ├── response_routes.py  # Submission handling & retrieval
│   ├── schema_routes.py    # Auto-detection triggers
│   └── webhook_routes.py   # Webhook endpoint registrations
├── analysis_engine.py      # Analytics aggregation pipelines
├── app.py                  # Entrypoint & Flask application factory
├── auth.py                 # API Key hashing & route protection decorators
├── config.py               # Development / Production settings
├── exporter.py             # CSV & PDF export formats
├── scheduler.py            # Background scheduler helper
├── schema_detector.py      # Database sampling schema inference logic
├── webhook_dispatcher.py   # Outbound webhook delivery mechanism
├── seed_demo_data.py       # Helper script to populate MongoDB
├── Dockerfile              # Docker container configuration
├── docker-compose.yml      # Orchestration definition (App + MongoDB)
├── Makefile                # Shorthand terminal commands
└── requirements.txt        # Python dependency manifest
```

---

## Getting Started

### Prerequisites

- [Docker](https://www.docker.com/) & [Docker Compose](https://docs.docker.com/compose/)
- Alternatively: **Python 3.10+** and a running **MongoDB** instance

### Local Installation (No Docker)

1. **Clone & enter the repository**
2. **Set up a Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Configure Environment Variables**:
   Create a `.env` file from the example:
   ```bash
   cp .env.example .env
   ```
4. **Run the Application**:
   ```bash
   python app.py
   ```

---

## Running with Docker (Recommended)

Running with Docker initializes both the Flask web server and a MongoDB instance automatically.

We provide a `Makefile` to simplify command execution:

- **Build and run in the background**:
  ```bash
  make up
  ```
- **Seed the database with sample responses**:
  ```bash
  make seed
  ```
- **View application logs**:
  ```bash
  make logs
  ```
- **Stop running services**:
  ```bash
  make down
  ```

Run `make help` to see a full list of utility commands.

---

## Core API Endpoints

All protected endpoints require your API key passed in the header: `X-API-Key: <your_key>`.

### Authentication

*   `POST /api/auth/keys` — Generate a new API key (displayed once in response).
*   `GET /api/auth/keys` — List all generated keys.
*   `DELETE /api/auth/keys/<id>` — Revoke a key.

### Analysis Definitions

*   `POST /api/analysis` — Save a new analysis definition mapping target collection and steps.
*   `GET /api/analysis` — List all definitions.
*   `POST /api/analysis/<id>/run` — Execute an analysis definition. Supports `?use_cache=true` to read the latest stored run.
*   `GET /api/analysis/<id>/results/latest/export?format=pdf|csv` — Downloads the latest analytics report.

### Schema Detection

*   `GET /api/schema/detect/<collection_name>` — samples a collection and suggests a runnable analysis configuration.

---

## Step Types Guide

Configure analysis definitions with any of these step types inside the `steps` list:

| Step Name | Key Parameter | Description |
| :--- | :--- | :--- |
| `frequency` | `field` | Distribution counts & percentages for a categorical field. |
| `array_frequency` | `field` | Distribution counts for array entries (multi-select / checkboxes). |
| `aggregate` | `field`, `operation` | Numeric operations: `avg`, `sum`, `min`, `max`, `count`. |
| `crosstab` | `row_field`, `col_field` | Cross-tabulation table of two categorical fields. |
| `nps` | `field` | Evaluates scores 0-10, classifying Promoters, Passives, Detractors, and returns final NPS. |
| `time_series` | `date_field`, `period` | Groups records by `hour`, `day`, `week`, `month`, `quarter`, `year`. |
| `funnel` | `stages` | Drop-off analysis over a pipeline of sequential filter stages. |
| `summarize` | `field` | Stata-style summary including mean, variance, skewness, kurtosis, and percentiles (1%, 5%, 10%, 25%, 50%, 75%, 90%, 95%, 99%). |
| `tabulate_chi2`| `row_field`, `col_field` | Cross-tabulation with Pearson Chi-Squared test of independence and p-value. |
| `regress` | `field_y`, `field_x`/`fields_x`, `hettest` | OLS linear regression (supports both simple and multivariable regression). Optionally executes a Breusch-Pagan homoskedasticity test (`hettest`). |
| `ttest` | `field`, `group_field` | Welch's t-test comparing means of a numeric variable grouped into two distinct categories. |
| `pwcorr` | `fields`, `sig` | Stata-style pairwise correlation matrix with optional significance p-values for multiple numeric fields. |
| `tabstat` | `fields`, `by`, `statistics` | Grouped summary table for multiple fields with statistics (mean, count, sum, sd, var, min, max, median, p25, p75). |
| `codebook` | `fields` | Diagnostic data profile identifying types, missing values, unique values, percentiles (numeric), or frequencies (categorical). |
| `oneway_anova` | `field`, `group_field` | One-way Analysis of Variance (ANOVA) comparing means across three or more categories with complete F-test table. |
| `transform` | `transformations` | In-pipeline data transformation step implementing `log`, `sqrt`, `center`, `zscore`, and `recode` operations. |
