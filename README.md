# GridSense AI

**An intelligent microgrid command center for hourly demand estimates and operator decision support.** GridSense AI validates 24 hours of weather-feature input, returns demand estimates, applies the official HackSphere controller rules on the backend, and explains the resulting mode and overload status for every hour.

> This workspace build is a working local prototype. Zoho QuickML credentials, a published QuickML endpoint, live weather, battery telemetry, grid hardware, and a Catalyst deployment were not available during implementation. When QuickML is not configured, the app uses a local model fitted on the supplied official training CSV and labels those predictions as a demonstration. No physical infrastructure is controlled.

## Start here: first-time setup and commands (Windows PowerShell)

Run each numbered step from the project root, in order. Do not change into the nested `HackSphere_Starter_Kit` folder. Stop if a command reports an error and fix it before moving to the next step. If `.venv` already exists, skip Step 2.

**1. Open the project folder and check Python:**

```powershell
# Replace this example with the actual current folder path.
cd "C:\path\to\smart-energy-microgrid"
python --version
```

Use the current project folder, not its former OneDrive location. You can open PowerShell there by typing `powershell` in the File Explorer address bar. If the project was moved, recreate its virtual environment instead of relying on the moved environment; keep the old environment until the new one works.

Python 3.11 or newer is required. If `python --version` shows an older version, install a supported Python version and reopen PowerShell.

**2. Create the virtual environment and install dependencies (first time only):**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**3. Run the official check and application tests:**

```powershell
.\.venv\Scripts\python.exe test_eval.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`test_eval.py` should end with `SUCCESS`. If you have Node.js installed, you can also check the frontend JavaScript syntax; Node is not required to run the app:

```powershell
node --check frontend\app.js
```

**4. Start the dashboard:**

```powershell
$env:HOST = "127.0.0.1"
$env:PORT = "5000"
.\.venv\Scripts\python.exe -m backend.server
```

Wait until the terminal prints `GridSense AI listening on http://127.0.0.1:5000`, then leave that terminal running while using the app. If the PowerShell prompt returns or the terminal prints `Shutdown requested`, the server has stopped; run the command above again and keep that terminal open. Open <http://127.0.0.1:5000>. For a first demo, choose **Telemetry & data → Official sample → Load official sample → Generate forecast**. To create a new 24-hour dataset, choose **Guided entry**, name it, enter a date as `DD-MM-YYYY`, choose a start hour such as `13:00`, set the numeric defaults, create the table, and edit rows as needed. To import existing energy rows, choose **Import CSV, TSV, or JSON**. Without QuickML credentials, forecasts use the explicitly labelled local demo model. Press **Ctrl+C** in the server terminal when you want to stop it.

If the VS Code embedded browser stays blank, first confirm the server terminal still shows it is listening and has not returned to a PowerShell prompt. Then refresh the preview or open `http://127.0.0.1:5000` in Edge or Chrome. When a browser reaches the app, the server terminal should log requests for `/`, `/styles.css`, `/intake.css`, `/app.js`, and `/api/health`. If those lines do not appear, the browser preview is not connecting to the local server. Do not start a second server on the same port.

**5. Optional: run the prediction CLI.** Open a second PowerShell window in the project root and run:

```powershell
.\.venv\Scripts\python.exe predict.py --input sample_test_input.csv --output predictions.csv
```

That command predicts all 1,000 rows in the official sample file and writes `predictions.csv` with the required `timestamp,target_demand_kw` columns. Without `QUICKML_ENDPOINT_URL`, the printed `DEMO FALLBACK` warning means the output came from the local model, not QuickML.

**6. Optional: inspect the data and local demo-model metrics.**

```powershell
.\.venv\Scripts\python.exe scripts\inspect_data.py
.\.venv\Scripts\python.exe scripts\evaluate_local_model.py
```

The first command summarizes the official CSV files. The second calculates local-model holdout metrics; neither command is needed just to start the dashboard.

## Troubleshooting startup and QuickML

The commands above explicitly select port **5000**. The server defaults to **5000** when `PORT` is absent; setting it explicitly keeps the launch command clear. Catalyst's `X_ZOHO_CATALYST_LISTEN_PORT`, when provided, takes precedence over `PORT`. Restart the server after changing environment variables, and keep its terminal open.

For a blank page or “Failed to fetch”, run these commands in a second PowerShell terminal:

```powershell
Test-NetConnection 127.0.0.1 -Port 5000
Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" | ConvertTo-Json -Depth 6
(Invoke-WebRequest -Uri "http://127.0.0.1:5000/app.js" -UseBasicParsing).StatusCode
Get-NetTCPConnection -LocalPort 5000 -State Listen | Select-Object LocalAddress, LocalPort, OwningProcess
```

Confirm the health response identifies **GridSense AI** and the JavaScript request returns HTTP 200. An open port alone may belong to another application. Open the same host and port used by the Python server and hard-refresh the browser. Check its Console and Network panels for failed assets or API requests. Do not open `frontend/index.html` directly or serve the frontend separately: its relative `/api/...` requests require the Python backend on the same origin. Inspect the Python terminal for errors. Do not stop unrelated processes merely to free a port. Port 8080 was reported to show a blank page on the user's machine; its cause has not been established, and changing ports alone does not diagnose it.

“QuickML endpoint set” means only that `QUICKML_ENDPOINT_URL` is nonempty; the indicator remains amber. Older versions displayed “QuickML configured” with a green indicator. Neither label proves that the URL is valid, reachable, authenticated, or able to predict. A “Could not reach the configured QuickML endpoint” error means the backend's outbound HTTP request failed; check the endpoint URL, DNS, proxy, TLS trust, and network access from the machine running Python. Keep TLS verification enabled. A separate “Failed to fetch” browser message concerns browser-to-backend communication and needs its own network check.

To isolate QuickML from the local application, stop the server, then use this command in its PowerShell session and restart on port 5000:

```powershell
Remove-Item Env:QUICKML_ENDPOINT_URL -ErrorAction SilentlyContinue
$env:PORT = "5000"
.\.venv\Scripts\python.exe -m backend.server
```

Load the official sample and generate a forecast. This explicitly selects **local demonstration mode**, not a repaired QuickML integration. To use QuickML again, stop the server, restore the real published endpoint and required authentication in the server process, and restart. Never use placeholder values as real endpoint settings. Merely copying `.env.example` to `.env` has no effect: this application does not automatically load `.env`.

Verify the published model in Catalyst's endpoint tester first. Use its exact endpoint URL, region, environment, authentication headers, feature schema, and request/response examples. The current adapter sends `{"data":[...]}` and accepts `{"predictions":[...]}` or `{"status":"success","result":[{"prediction":...}]}`. Those are the adapter's implemented formats, not a guarantee that every published QuickML endpoint uses them. If the endpoint tester specifies a different format, the adapter requires a reviewed code change. Do not substitute a console page URL for an inference URL. A successful connection must return one finite numeric demand prediction for each input row; generating and restoring a 24-hour QuickML-labelled forecast is the end-to-end check.

HTTP 401/403 from the inference service indicates authentication or authorization needs investigation; check the endpoint key, OAuth scope/expiry, organization, and deployment environment. HTTP 429 indicates rate limiting. Timeouts and network failures are different from response-schema errors. The adapter deliberately does not silently switch to the local model after a configured QuickML request fails. Previously saved datasets can be loaded and retried after fixing the connection.

## Project overview

The challenge is to forecast hourly electricity demand and translate each predicted value into a Main Grid or Renewable Storage recommendation. The application supports guided 24-hour entry, CSV/TSV/JSON imports, the official test sample, point forecasts, the exact transition rules, operator alerts, data exports, a rule-based copilot, saved input sets and forecasts, model status, and a persisted light/dark theme.

The interface is a responsive operations dashboard. It shows only calculated values after a forecast exists. Historical readings, input weather rows, demand estimates, battery information, and live telemetry are not conflated: the current app has no real telemetry integration, and battery state is explicitly unconfigured.

## Existing starter kit inventory

The root files and the extracted `HackSphere_Starter_Kit/` copies of the five official files were byte-identical at inspection. `HackSphere_Starter_Kit.zip` contains those same five files. The nested copies and ZIP are preserved unchanged. The root `predict.py` was updated in place to use the model adapter while preserving `predict(input_df)`; its original starter version remains in `HackSphere_Starter_Kit/predict.py` and the ZIP. The official self-test and problem statement remain unchanged.

The supplied datasets were inspected with `python scripts/inspect_data.py`:

| File | Shape | Validation findings | Time span |
| --- | ---: | --- | --- |
| `train_telemetry.csv` | 4,000 × 5 | No missing values, duplicate rows, duplicate timestamps, invalid timestamps, non-numeric values, or non-hourly gaps | 2014-12-31 23:00:00 through 2015-06-16 14:00:00 |
| `sample_test_input.csv` | 1,000 × 4 | No missing values, duplicate rows, duplicate timestamps, invalid timestamps, non-numeric values, or non-hourly gaps | 2015-06-16 15:00:00 through 2015-07-28 06:00:00 |

The training target has a mean of **156.574 kW**, median **153.685 kW**, interquartile range **108.112–196.782 kW**, and range **51.10–306.33 kW**. Feature ranges are −1.40–38.30 °C, 39.32–100% humidity, and 0–488 W/m² irradiance. The sample input contains features only; it has no ground truth, and this project does not fabricate any.

## Official starter-kit files

| File | Role |
| --- | --- |
| `PROBLEM_STATEMENT.md` | Competition requirements and source of truth for feature schema, prediction contract, and transition rules. |
| `train_telemetry.csv` | The 4,000 official training observations and `target_demand_kw` target. Used by the local demo model and the documented QuickML setup. |
| `sample_test_input.csv` | The 1,000 official feature-only test rows. The UI demo loads its first 24 rows; `predict.py` can infer all rows. No target values are invented. |
| `predict.py` | Evaluation-compatible `predict(input_df)` returning one finite NumPy prediction per input row. It can also write the required two-column prediction CSV. |
| `test_eval.py` | Original official pre-submission script, preserved and run unchanged. |

## Implemented features

- Backend validation of guided rows and CSV, TSV, or JSON feature data, including readable header aliases, date/time combinations, numeric and finite weather values, uniqueness, and consecutive hourly ordering for the app's 24-hour workflow.
- Strict physical validation bounds: temperature −80 to 60 °C, humidity 0 to 100%, and solar irradiance 0 to 2,000 W/m². These are documented rejection bounds, not measured site limits.
- QuickML integration boundary using the endpoint and authentication headers described in the Catalyst documentation. When configured, QuickML errors are returned to the user; they never silently fall back.
- Local demonstration model candidates (HistGradientBoosting and RandomForest) trained from the supplied dataset. A chronological 80/20 split selects the candidate by RMSE; the selected model is refit on all training rows. Predictions and metrics are labelled local demo output, never QuickML output.
- Backend transition controller, critical alerts, summary metrics, peak and average demand, mode counts, attention hours, and per-hour explanation text.
- Data-backed demand SVG chart with switching/critical thresholds and keyboard-accessible point tooltips; mode timeline; forecast distribution; sortable/filterable table; alert filter; and CSV exports.
- Rule-based GridSense Copilot that only uses the current forecast and controller thresholds. No generative AI provider is configured.
- Dark, light, and system themes, persisted in local storage; responsive navigation and mobile layouts.
- Model, weather, battery, and hardware integration statuses presented accurately. No battery readings, causal weather claims, or live-system claims are invented.
- Guided manual entry with date, start-hour, numeric measurement hints, editable hourly rows, downloadable file templates, and clear validation errors.
- SQLite persistence for named 24-hour data sets and completed forecast history. Users can reload data and reopen results after a server restart on the same local workspace.

## Architecture and folder map

```text
smart-energy-microgrid/
├── PROBLEM_STATEMENT.md             # Official source of truth
├── train_telemetry.csv              # Official training data
├── sample_test_input.csv            # Official feature-only test data
├── predict.py                       # Evaluation-compatible entry point
├── test_eval.py                     # Preserved official evaluator
├── HackSphere_Starter_Kit/           # Original extracted starter files, unchanged
├── HackSphere_Starter_Kit.zip        # Original archive, unchanged
├── backend/
│   ├── grid_engine.py                # Input checks, decisions, summaries
│   ├── model_service.py              # QuickML adapter and local demo model
│   ├── store.py                      # Local SQLite data-set and forecast history
│   └── server.py                     # API and static frontend server
├── frontend/
│   ├── index.html                    # Dashboard sections and controls
│   ├── styles.css                    # Responsive dark/light design system
│   ├── intake.css                    # Guided entry and import layouts
│   └── app.js                        # Interactions, charts, exports, copilot
├── tests/                            # unittest engine, API, store, and model tests
├── scripts/
│   ├── inspect_data.py               # Reproducible dataset profile
│   ├── evaluate_local_model.py       # Local demo-only holdout metrics
│   └── stage_catalyst.py              # Safe AppSail source staging
├── docs/architecture.md             # Mermaid architecture diagram
├── .env.example                      # Names only; no credentials
├── requirements.txt
└── Procfile
```

The UI and API are served from one Python AppSail process. The backend owns validation, inference orchestration, response checks, transition decisions, and overload alerts. The frontend renders results and gathers input. See [the architecture diagram](docs/architecture.md).

## Dataset and local model evaluation

The supported energy-model input fields are `timestamp`, `ambient_temp_c`, `humidity_pct`, and `solar_irradiance_wm2`. The training target is `target_demand_kw`. App inputs accept timestamps such as `YYYY-MM-DD HH:MM` or `DD-MM-YYYY HH:MM`, or separate `date` and `time`/`hour` fields. The API normalizes them to `YYYY-MM-DD HH:MM:SS`. The optional data-inspection command in Step 6 above prints a reproducible profile of both official CSVs.

### Use a new or fictional energy data set

Open **Telemetry & data → Guided entry**, name the data set, enter the start date as `DD-MM-YYYY` and the first hour as `HH:00`, then provide numeric temperature, humidity, and solar irradiance values. Those defaults fill 24 consecutive rows; edit any row before saving or forecasting. The helper text under each field gives the expected format, units, and validation range.

You can also import a `.csv`, `.tsv`, or `.json` file, paste data in one of those formats, or download a blank 24-hour template. Use one row per hour and provide date/time plus the three energy features. Common headings such as `date`, `time`, `temperature`, `humidity`, and `irradiance` are accepted. The app validates exactly 24 consecutive hourly rows before forecasting. Extra columns are ignored.

The current predictor only understands those three weather measurements and the timestamp. New fictional or site-specific rows can be passed through the same overview, forecast, controller, alert, and copilot views, but unrelated fields (for example, names, salaries, or arbitrary sensor columns) are not model inputs. Importing new rows does **not** retrain the predictor: without a configured QuickML endpoint, the local demo model remains trained on the official `train_telemetry.csv`. Treat fictional-data forecasts as demonstrations, not evidence of predictive accuracy for a new site. A site-specific deployment needs representative historical energy data with measured demand targets, model validation, and a published model trained for that site.

Saving a data set or generating its forecast stores the normalized rows in `data/gridsense.sqlite3`; forecast results are also saved and can be reopened from **Demand forecast → Forecast history**. This local SQLite store is for a single local workspace/server. It is not shared between users or instances and is not configured as durable Catalyst storage.

The fallback model derives cyclical hour, day-of-year, and weekday features from the supplied timestamp plus the three official numeric features. Training and inference use the same transform. The optional local-evaluation command in Step 6 above prints its chronological holdout metrics.

These metrics describe only the local demonstration model on a time-ordered holdout from the provided training file. They are not QuickML results, hidden-test accuracy, or a guarantee of production performance. `sample_test_input.csv` has no target, so it is used only to check feature validation and the prediction contract.

In this workspace run, the selected local candidate was RandomForest with **13.921 kW RMSE** and **10.914 kW MAE** on the final 800 chronologically held-out training rows. These recorded values are for reproducibility only; the script recalculates them for the installed package versions.

## Local prediction and QuickML configuration

The prediction CLI and dashboard commands are listed in [Start here](#start-here-first-time-setup-and-commands-windows-powershell). The CLI uses QuickML if a published endpoint is configured; endpoint, authentication, timeout, malformed response, wrong output count, and non-finite prediction errors are reported instead of silently falling back.

To use QuickML locally, set the values in the current PowerShell session before starting the server; `.env.example` is a reference template and is not auto-loaded:

```powershell
$env:QUICKML_ENDPOINT_URL = "<published-endpoint-url>"
$env:QUICKML_ENDPOINT_KEY = "<endpoint-key>"
$env:ZOHO_OAUTH_TOKEN = "<oauth-access-token>"
$env:CATALYST_ORG = "<organization-id>"
$env:CATALYST_ENVIRONMENT = "Development" # Match the published endpoint environment.
$env:HOST = "127.0.0.1"
$env:PORT = "5000"
.\.venv\Scripts\python.exe -m backend.server
```

## API

All endpoints are same-origin with the dashboard.

| Method and route | Purpose |
| --- | --- |
| `GET /api/health` | Backend status and non-secret integration configuration flags. It does not claim QuickML is healthy without a successful inference. |
| `GET /api/sample` | First 24 valid rows from the official `sample_test_input.csv`, explicitly identified as sample input. |
| `GET /api/datasets` / `GET /api/datasets/{id}` | List saved data sets or load one with its validated rows. |
| `POST /api/datasets` / `DELETE /api/datasets/{id}` | Save a named 24-row input set or delete it. Saved forecast records remain available after deleting the input set. |
| `GET /api/forecasts` / `GET /api/forecasts/{id}` | List forecast history or load a complete saved result. |
| `POST /api/validate` | Validates `{"data_text":"...","format":"csv|tsv|json"}` or canonical `{"rows":[...]}` and returns all normalized rows plus a five-row preview. |
| `POST /api/forecast` | Accepts a saved `{"dataset_id":"..."}` or validated rows/text. New inputs are saved before inference. Returns estimates, per-hour mode/reason/alert, calculated summary, model source, input source, data-set ID, and generation time. |

The app forecast route requires exactly 24 unique, consecutive hourly rows in ascending order. Example request:

```json
{
  "rows": [
    {
      "timestamp": "2025-01-01 00:00:00",
      "ambient_temp_c": 21.5,
      "humidity_pct": 54.0,
      "solar_irradiance_wm2": 0.0
    }
  ],
  "source": "Operator CSV"
}
```

The example shows the row shape; the app API requires 24 rows for an actual forecast. CSV, TSV, and JSON file parsing is handled by `/api/validate` or `/api/forecast` using `data_text` and `format`. The official `predict(input_df)` callable accepts any non-empty supported batch up to 5,000 rows so `test_eval.py` can evaluate the full 1,000-row sample.

## Transition controller

The backend evaluates every row independently using the official rules:

- **Renewable Storage Mode:** predicted demand is strictly greater than 160 kW **or** the hour is 18:00–22:00 inclusive.
- **Main Grid Mode:** predicted demand is at most 160 kW and the hour is outside 18:00–22:00.
- **Critical Overload Alert:** predicted demand is at least 200 kW, independent of mode.

The rule module and exact boundaries are covered by automated tests. These are software decision signals only; no battery or electrical switch is operated.

## Zoho Catalyst QuickML setup

Live QuickML inference has **not** been verified from this workspace. The supplied Catalyst screenshots show the prediction pipeline as Not-Executed, with no operations configured and Endpoint Created: No. Complete training and endpoint creation before configuring this pipeline for inference; these screenshots do not establish the current state of other projects or environments. To connect the actual service:

1. In Catalyst QuickML, create a regression pipeline from the unmodified official `train_telemetry.csv`; choose `target_demand_kw` as the target and use the official four input fields.
2. Inspect the `timestamp` handling in QuickML. If QuickML requires a transformation, apply the same deterministic transform for both training and endpoint inference. Do not introduce uncomputed lag or rolling features.
3. Evaluate on a chronological holdout where supported. Record the actual QuickML metrics from Catalyst; do not copy the local demo metrics.
4. Publish a model version and copy the endpoint URL, endpoint key, and OAuth access token with the `QuickML.deployment.READ` scope. Confirm the endpoint's request schema with its model tester before integration. The adapter sends the starter kit's batch request body (`{"data":[...]}`) and accepts its `{"predictions":[...]}` response, as well as the implemented SDK-style `{"status":"success","result":[{"prediction": ...}]}` response. The endpoint detail page's sample request and response remain authoritative for the specific model.
5. Configure these environment variables in the backend/AppSail service, not frontend JavaScript:

```text
QUICKML_ENDPOINT_URL=<published endpoint URL>
QUICKML_ENDPOINT_KEY=<endpoint key>
ZOHO_OAUTH_TOKEN=<Zoho OAuth access token>
CATALYST_ORG=<Catalyst organization identifier>
CATALYST_ENVIRONMENT=Development
```

The current adapter includes the endpoint key and Catalyst OAuth headers when values are supplied. Check the endpoint detail page to confirm which values its POST request requires: `X-QUICKML-ENDPOINT-KEY`, `Authorization: Zoho-oauthtoken ...`, `CATALYST-ORG`, and `Environment`, and verify the required OAuth scope (the existing integration guide specifies `QuickML.deployment.READ`). See [QuickML Pipeline Endpoints](https://docs.catalyst.zoho.com/en/quickml/help/pipeline-endpoints/).

Use your organization's approved token rotation and secret-storage process. Do not commit `.env`, access tokens, endpoint keys, or real configuration values. An endpoint URL alone is not evidence of a successful integration; the app only reports a QuickML forecast after a valid endpoint response.

## Local validation and tests

Run the checks in Step 3 of [Start here](#start-here-first-time-setup-and-commands-windows-powershell) from the project root. The JavaScript syntax check in that section is optional and only requires Node.js.

Tests cover the official transition boundaries, inclusive evening hours, independent critical alerts, CSV/TSV/JSON parsing, timestamp formats, ranges, missing/nonnumeric values, empty and malformed data, duplicate headers/rows, forecast ordering, saved-data and forecast-history round trips, API error status, endpoint auth headers/failures, and finite prediction output. The QuickML tests use mocks; they do not claim a real Catalyst request. There is no configured browser automation test framework in this starter project.

## Deploy to Zoho Catalyst AppSail

The app is structured as a single Python service serving both the dashboard and API; this avoids a browser-exposed model credential and a separate CORS boundary. Catalyst account entitlements, runtime availability, and the required disk/memory should be checked before deployment. Catalyst's current AppSail docs list Python managed runtimes, require the service to listen on `X_ZOHO_CATALYST_LISTEN_PORT`, and permit application-specific startup commands and environment variables. See [Python AppSail overview](https://docs.catalyst.zoho.com/en/serverless/help/appsail/help-guides/python/overview/) and [AppSail configuration](https://docs.catalyst.zoho.com/en/serverless/help/appsail/appsail-configurations/).

1. Create an isolated deployment source directory. This copies only the required app source and official files and refuses to overwrite an existing path:

   ```powershell
   .\.venv\Scripts\python.exe scripts\stage_catalyst.py --output appsail_build
   ```

2. Install and log in to the current Catalyst CLI, create/select the project in the Catalyst console, then initialize or add an AppSail Python service using `appsail_build` as its source directory.
3. Build dependencies for the AppSail Linux/Python runtime. Catalyst's Python examples package dependencies into the service source. On Linux or WSL matching the selected Python runtime, install dependencies into the included `.app_deps/` directory:

   ```bash
   python3 -m pip install -r requirements.txt -t .app_deps
   ```

   Do not copy Windows-compiled wheels to a Linux service. Include `.app_deps/` in the deployment source and set the AppSail startup command to `sh -c 'PYTHONPATH=.app_deps python3 -u -m backend.server'` (or the equivalent command supported by the selected CLI/runtime). The application reads Catalyst's listen-port variable automatically.
4. Configure the five QuickML variables in the AppSail environment settings after publishing and verifying the QuickML endpoint. Keep secrets out of the source bundle and client code.
5. Deploy the service from the Catalyst CLI or console. Confirm AppSail is running and test `GET /api/health`, `GET /api/sample`, then a 24-row `POST /api/forecast` against the **deployed URL**.
6. Only after the page and forecast request succeed, record the real public development/production URL. No deployment URL is available from this implementation session.

The model's first local request fits two small candidate estimators in-process. Confirm that AppSail's memory and disk limits fit the selected dependencies and data; increase them in Catalyst if the measured footprint requires it. The included SQLite history is local and suitable for a single instance only. Before multi-user or production operation, use managed durable storage, authentication/authorization, backups and retention, monitored inference, load testing, and a site-validated model. Those services are not configured here.

## Known limitations and future integrations

- **QuickML:** integration adapter and setup are implemented; actual model training, endpoint publication, and authenticated inference remain unverified until credentials and a published URL are supplied.
- **Deployment:** Catalyst AppSail-ready layout and instructions are included; this project has not been deployed and has no verified public URL.
- **Fallback:** a local estimator is trained from the official training data and reported as a demo. Its holdout metric is calculated, not claimed as the competition model's accuracy.
- **Forecast input:** users must provide a valid feature row for each forecast hour; there is no live weather API and no invented weather interpolation. The supported model schema is fixed to timestamp plus ambient temperature, humidity, and solar irradiance.
- **Hardware and battery:** there is no dispatch integration, live state of charge, battery-capacity model, or physical switching. The official transition result does not control equipment.
- **Uncertainty and AI:** predictions are point estimates without quantified uncertainty; the copilot is rule-based and does not call a language-model API.
- **Persistence/access control:** data sets and forecast history are saved in a local SQLite file, but there is no account login, authorization, multi-instance coordination, managed backup, or configured durable server storage. Add those with the intended Catalyst services before multi-user production use.

## Demo walkthrough for judges

1. Open **Telemetry & data** and load the official sample, or create/import a 24-hour fictional energy data set. Point out the 24 accepted rows and the schema/provenance notes.
2. Generate the forecast. State clearly that, until a site-trained QuickML model is configured, this is the local demonstration model trained on the supplied training CSV; importing new data does not retrain it.
3. On **Overview**, explain the actual peak and average, the forecast curve, the 160 kW threshold, the 200 kW alert line, and how each hour maps onto the mode timeline.
4. Open **Grid controller** and show the row-level reason plus the independent overload column.
5. Filter **Alerts & events**, then ask **GridSense Copilot** to summarize the forecast or explain a mode change.
6. Export the two-column predictions CSV and the separate detailed decision report. Open **Model health** to show the correct model source and the measured local chronological-holdout metric.
7. Toggle light mode and resize to mobile to show the responsive view. Close by noting that there are no live weather, battery, or hardware connections yet.

## Submission readiness

- [x] Official starter kit inspected and preserved; root and extracted copies were byte-identical.
- [x] Official training data and feature-only sample inspected; app and `predict.py` use the supplied assets.
- [x] `predict(input_df)` keeps the official return type, input order, timestamp pairing, and finite one-prediction-per-row behavior.
- [x] Backend controller implements exact thresholds and inclusive hours with boundary tests.
- [x] Frontend, backend, guided entry, CSV/TSV/JSON imports, saved datasets/history, charts, export, themes, alerts, and rule-based copilot implemented.
- [x] README, API notes, environment template, and architecture diagram included.
- [ ] QuickML training and publishing: requires the user's Catalyst account and setup.
- [ ] Live AppSail URL: requires Catalyst account access and deployment.
- [ ] Live weather, battery telemetry, and grid switching: unconfigured optional integrations.

