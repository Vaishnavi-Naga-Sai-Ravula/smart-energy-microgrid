# QuickML authentication and verification

The India-region endpoint was verified with a batch request shaped as
`{"data": [{"timestamp": "YYYY-MM-DD HH:MM:SS", "ambient_temp_c": 20,
"humidity_pct": 50, "solar_irradiance_wm2": 0}]}` and a response shaped as
`{"status": "success", "pipeLineType": "prediction", "result": [95.34]}`.
The adapter already accepts this numeric result array and validates count and
finite values. It never switches to the demo model after a configured request fails.

Configure these variables in the backend environment, never frontend JavaScript:

- `QUICKML_ENDPOINT_URL`: exact HTTPS prediction URL from the published endpoint.
- `QUICKML_ENDPOINT_KEY`: private endpoint key.
- `CATALYST_ORG`: organization identifier from required headers.
- `CATALYST_ENVIRONMENT`: `Development` for the tested deployment.
- `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`: renewable OAuth credentials.
- `ZOHO_ACCOUNTS_URL`: `https://accounts.zoho.in` for the India account.

Authorize the refresh token with `QuickML.deployment.READ`. The backend requests
an access token on first inference and caches it until shortly before expiry.
Each process maintains its own cache; credentials must be available again after
restart. Configure all three refresh credentials together. When none are set,
the existing `ZOHO_OAUTH_TOKEN` static access-token mode still works, but expires
without automatic renewal. Refresh credentials take precedence over static tokens.
Only official Zoho Accounts HTTPS destinations are accepted; TLS checks remain
on and redirects are refused. Token failures are reported without response secrets.
Revoked credentials require replacement; renewal does not provide user login,
data authorization, or other production capabilities.

The application does not automatically load `.env`. AppSail runtime variables
must be set in its configuration; local PowerShell environment variables only
apply to that session and child processes. Do not put actual credentials in
`app-config.json`, source, commits, deployment archives, or shared screenshots.
Rotate credentials that were exposed. Keep durable credentials in secure backend
settings or an appropriate secret manager, subject to your platform's access controls.

After setting runtime variables, restart the backend as required by the platform.
Verify a real deployed forecast with:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py --base-url "https://YOUR-APP-URL" --require-quickml
```

This checks 24 finite ordered predictions and saved forecast restoration and must
report `Zoho Catalyst QuickML`. Health/configuration indicators alone do not prove
inference works. The test leaves a labelled dataset and forecast.

Run the official `test_eval.py` with QuickML configured to verify the evaluator's
prediction contract. For the competition CLI, `predict.py --input
sample_test_input.csv --output predictions.csv` must produce one prediction per
row in input order. Batch service limits for the full 1,000-row input still need
live verification; successful two-row or 24-row requests do not establish them.

Unit tests mock OAuth renewal and inference; passing them does not establish
live refresh-credential validity or AppSail configuration. Validate an actual
refresh grant locally, then a deployed forecast, before claiming integration.
