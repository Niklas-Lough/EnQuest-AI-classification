# EnQuest BBSS Classification Webjob — Deployment Handover

The historical backfill has been run manually and is complete. What's left is deploying the daily scheduled job in Fennex Azure so new cards get classified automatically going forward. This doc explains how the code works, then how to deploy it.

## 1. How the code works (brief)

- `taxonomy.json` — the classification rules (15 Hazard labels, 11 Human Factors labels, keyword triggers, precedence rules). Editable without a code change.
- `prompt.py` — builds the Agent instructions text and a reference JSON schema from the taxonomy file.
- `classifier_client.py` — calls the Azure AI Foundry Agent (`EnQuestObservationClassifier`) via the OpenAI Responses API and parses its response.
- `sql_engine.py` — all `dbo.FormData_Master` access: adds the `AI_Hazard_Category` / `AI_Human_Factors_Category` columns if missing, fetches unclassified cards, writes results back, and logs Low-confidence results to `dbo.AI_Classification_Review_Log`.
- `process_batch.py` — classifies a batch of cards concurrently, with a bounded confidence-retry (a card is retried up to 2 extra times if Low confidence, then persisted regardless and flagged for review if still Low).
- `classify.py` — the shared `classify_observations(force, limit, concurrency)` function both entry points call.
- `main.py` — **this is the daily webjob entry point.** Runs `classify_observations(force=False)`, i.e. only classifies cards not yet classified. Safe to run daily indefinitely.
- `backfill.py` — the manual/on-demand entry point used for the historical run (not needed for the daily job, but useful if a taxonomy change requires a `--force` reclassify later).

Full background on the taxonomy and design decisions is in `ENQUEST_BBSS_AI_CLASSIFICATION.md` in this repo — worth a read before deploying.

**Important agent-specific detail:** the Foundry Agent's classification instructions live in the Agent's own portal configuration (Instructions field), not in a per-call API parameter — this Agent type rejects instruction overrides on the request. If the taxonomy ever changes, run `python agent_setup.py` locally to print the updated instructions and paste them into the Agent's Instructions field in the Foundry portal. The webjob itself doesn't need to know about this — it's a one-time manual step per taxonomy change.

## 2. Prerequisites before deploying

- The Foundry Agent (`EnQuestObservationClassifier`) already exists in the Foundry project and its Instructions are up to date (see above).
- `dbo.FormData_Master` already has the `AI_Hazard_Category` / `AI_Human_Factors_Category` columns and `dbo.AI_Classification_Review_Log` table (created automatically by `ensure_schema()` on first run — no manual DB step needed, but worth knowing it'll `ALTER TABLE` on its very first execution).
- Note the actual values you'll need for step 4 below: the Azure SQL connection string, the Foundry project endpoint, and the Agent name.

## 3. Deployment steps

This mirrors the existing `SPA-DemoInd-Classification-Webjob` already running in this App Service for the other customer — same pattern, just pointed at different files/config. If anything below is unclear, that existing webjob is a working reference to compare against.

### 3.1 Set Application Settings (environment variables)

In the Azure Portal, go to the App Service → **Configuration** → **Application settings**, and add:

| Name | Value |
|---|---|
| `BBSS_PROD_CONNECTION` | The SQLAlchemy connection string (see note below) |
| `BBSS_FOUNDRY_PROJECT_ENDPOINT` | The bare Foundry project endpoint, e.g. `https://<resource>.services.ai.azure.com/api/projects/<project-name>` |
| `BBSS_FOUNDRY_AGENT_NAME` | `EnQuestObservationClassifier` |

`BBSS_PROD_CONNECTION` must be a SQLAlchemy URL, not a raw ADO.NET string — if building it fresh, use the `odbc_connect` form (`mssql+pyodbc:///?odbc_connect=<url-encoded ODBC string>`) to avoid special-character issues in the password. **Do not** put these values in a `.env` file — that only works for local dev (`python-dotenv`); in Azure they must be real Application Settings, which `os.environ` picks up directly.

### 3.2 Set up authentication to the Foundry Agent — do not skip this

Locally, the code authenticates via `DefaultAzureCredential`, which picks up your `az login` session. **There is no interactive login in Azure** — the App Service needs its own identity, or every Foundry Agent call will fail with an authentication error even though everything else (including the SQL connection) works fine.

1. On the App Service → **Identity** → enable **System-assigned managed identity**. Save, note the generated Object (principal) ID.
2. In the Foundry project → **Access control (IAM)** → add a role assignment granting that managed identity a role with permission to call the Agent (e.g. **Azure AI Developer**, or whatever role the team you set the local `az login` account up under was using — check with whoever provisioned the Foundry project if unsure which role is minimally sufficient).

`DefaultAzureCredential` automatically tries Managed Identity when running inside Azure, so no code change is needed once this is granted — it's purely an Azure-side configuration step.

### 3.3 Deploy the code + webjob files

1. Deploy the repo (or at minimum: all `*.py` files, `taxonomy.json`, `requirements.txt`) to the App Service, under:
   `%HOME%\site\wwwroot\App_Data\jobs\triggered\BBSS-Classification-Webjob\BBSS_Classification_WebJob\`
   (this exact path is hardcoded in `run.cmd` — either deploy to this path or update the `JOB_PATH` variable in `run.cmd` to match wherever it actually lands).
2. `run.cmd` is the WebJob's run command — it installs `requirements.txt` on each run and then calls `main.py`. No changes needed unless the deployment path differs from the default above.
3. `settings.job` sets the schedule: `{"schedule":"0 0 6 * * *"}` — daily at 06:00 UTC (NCRONTAB format: second, minute, hour, day, month, day-of-week). Adjust the hour if a different time is preferred.

### 3.4 Verify the deployment

1. In the Azure Portal → App Service → **WebJobs**, confirm `BBSS-Classification-Webjob` shows up and is scheduled.
2. **Don't wait for the schedule** — use **Run** in the portal (or trigger via Kudu) to fire it once manually and watch the logs.
3. Check the WebJob's run output/logs for a line like `EnQuest classification run complete. Fetched=N Classified=N ...` — if `Fetched=0`, that's actually correct/expected once the backfill is complete and no new cards have come in since (idempotent skip is working as designed).
4. Spot-check in SQL that any newly-submitted cards since the backfill got `AI_Hazard_Category`/`AI_Human_Factors_Category` populated.
5. Confirm the ODBC driver referenced in the connection string (`ODBC Driver 17 for SQL Server`, or whichever was used) is actually available in the App Service's runtime — this bit us locally (a version mismatch caused pip to try to compile pyodbc from source). If the webjob fails on `pyodbc`/driver-related errors, check what's installed in that environment the same way we did locally: `python -c "import pyodbc; print(pyodbc.drivers())"` via Kudu's console, and adjust the connection string's `Driver=` value to match.

## 4. Ongoing operations

- **Monitoring**: each run logs a summary line (fetched / classified / failed / confidence-retried / confidence-resolved / confidence-exhausted counts) — worth keeping an eye on `confidence_exhausted` growing over time as a signal the taxonomy may need retuning.
- **Review log**: `dbo.AI_Classification_Review_Log` accumulates rows for cards still Low confidence after retries — this is the pilot's human-review queue, not an error log.
- **Taxonomy changes**: edit `taxonomy.json`, run `python agent_setup.py` locally, paste the new instructions into the Foundry portal's Agent configuration, then run `backfill.py --force` once to reclassify historical data under the new rules if needed. The daily webjob itself needs no changes for this.
