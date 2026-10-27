# Submission and deployment checklist

GridSense AI is a demand-forecasting and operator decision-support prototype.
It does not operate electrical equipment. Submit the functionality you can
demonstrate; do not claim live telemetry, proven energy savings, or capacity for
millions of users.

## 1. Verify the current source

Open PowerShell in the current project folder, then run:

```powershell
git pull --ff-only origin main
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe test_eval.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Use the name of your working virtual environment if it differs from `.venv`.
Stop if the pull reports a conflict; preserve local work. If the project was
moved, recreate the virtual environment as described in the README.

## 2. Prepare the AppSail source

```powershell
.\.venv\Scripts\python.exe scripts\stage_catalyst.py --output appsail_build
```

The directory must not already exist. Choose another unused name if needed.
The helper includes backend, frontend, official data, requirements, and the HTTP
smoke-test script. It excludes your local database, virtual environment, and
credentials. Do not upload the entire working folder.

In Catalyst, use an **AppSail Python service** for this combined backend and
frontend. Select a supported Python runtime of at least 3.11; the source was
validated here on Python 3.12, Linux x86_64. Availability, resource limits, and
account entitlements must be checked in your Catalyst console.

Build dependencies on Linux matching the selected Python runtime, from the
staged directory:

```bash
python3 -m pip install --no-cache-dir -r requirements.txt -t .app_deps
```

Include `.app_deps` in the service source and configure its startup command:

```sh
sh -c 'PYTHONPATH=.app_deps python3 -u -m backend.server'
```

Do not upload Windows-built NumPy/scikit-learn dependencies to Linux. Use
Catalyst's supported build process or a matching Linux/WSL environment. Do not
override Catalyst's `X_ZOHO_CATALYST_LISTEN_PORT`; the server uses it automatically
and binds to all interfaces by default in AppSail. Leave `HOST` unset in the
deployed service, or use `0.0.0.0`, rather than the local `127.0.0.1` example.

This repository has not yet been validated on an actual AppSail instance. A local
pass is not a deployed-service pass. Consult the current AppSail console/docs for
its upload and build settings; do not use a frontend-only static hosting service
for the Python API.

## 3. Choose and verify the model

- **Local demonstration:** leave `QUICKML_ENDPOINT_URL` unset. The first forecast
  fits the supplied training data; allow up to two minutes in the browser. This
  does not satisfy a requirement for actual QuickML inference.
- **QuickML:** finish configuring and executing the prediction pipeline, create
  its endpoint, and test it in Catalyst. Set the backend's actual URL and required
  authentication in AppSail settings. `.env` is not loaded automatically. The
  model target is `target_demand_kw`; request fields and response format must
  match the endpoint tester and adapter. Never put credentials in frontend code.

The inference hostname must be reachable from the deployed backend. The console
URL is not an inference URL. Expired tokens, certificate problems, proxy errors,
timeouts, and incorrect model schemas require different fixes. Do not disable
TLS verification or silently fall back after a configured QuickML failure.

## 4. Verify the actual deployed URL

From the laptop project root, replace the example URL with the AppSail URL:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --base-url "https://your-app-host"
```

If the submission requires QuickML, run:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --base-url "https://your-app-host" --require-quickml
```

The command fails on broken assets, unavailable storage/schema, rejected sample
input, unsuccessful forecasting, invalid predictions, or failed history restore.
It writes a labelled sample dataset and forecast to the target workspace. A
successful `--require-quickml` check requires an actual QuickML-labelled response;
it cannot pass by using the local demo model.

`/api/health` reports process/configuration status. `/api/ready` checks readable
storage/schema and required packaged files; it does not authenticate with QuickML
or prove future writes will succeed. The full smoke test verifies a real write
and forecast. Inspect AppSail logs if either fails.

## 5. Present a short, honest demonstration

1. Open the deployed URL and load the official 24-row sample.
2. Generate a forecast and identify the actual model source.
3. Explain the demand curve, 160 kW switching rule, inclusive evening window,
   and independent 200 kW overload alert.
4. Reopen a forecast from history and export its predictions.
5. Show an invalid input being rejected with a readable explanation.

Keep a recording of a verified demonstration as a backup if submission rules
allow it. State when data is historical and when the model is local.

## Limits and the path to a real pilot

This release has no user accounts or per-user authorization. All users of one
instance share its datasets/history and can delete datasets. Use non-sensitive
sample data for a public demonstration. SQLite storage is local to one service
instance and may be lost during deployment/replacement; do not rely on it for
durable records or run multiple replicas with independent copies as if shared.

Before a customer pilot, add authenticated user/site isolation, managed durable
storage and backups, a production application server, monitoring, rate limits,
and recovery tests. Validate forecasts on representative site data against a
simple baseline. Real-time weather and equipment feeds require explicit
integrations; the current app has neither. Prove scale with workload-specific
load tests and measured cost/latency before making capacity claims.
