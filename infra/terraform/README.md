# Terraform for GCP backend

This directory manages the backend infrastructure for this project on Google Cloud.

## Managed resources

- Required APIs (`Cloud Run`, `Artifact Registry`, `Cloud Build`, `IAM`)
- Artifact Registry Docker repository
- Cloud Run runtime service account
- Cloud Run service for `backend/backend.js`
- Cloud Build service account permission to push images (Artifact Registry writer)
- Optional public invoke permission (`allUsers`)

Cloud Build **GitHub triggers** are not managed by Terraform here; create them in the console (see below).

## Prerequisites

- Terraform `>= 1.6`
- `gcloud` CLI
- Access to project `daisuke-cafe-search`

Authenticate and set project:

```bash
gcloud auth application-default login
gcloud config set project daisuke-cafe-search
```

## 1) Prepare variables

Copy example variables and edit secret values:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Set at least:

- `container_image`

By default this Terraform uses Secret Manager refs in Cloud Run env:

- `MONGODB_CONNECTION_STRING` (version `latest`)
- `REACT_APP_GOOGLE_CLIENT_ID` (version `latest`)

If your secret names differ, set:

- `mongodb_connection_string_secret_name`
- `google_client_id_secret_name`

To use plain env vars instead (not recommended for production), set:

- `use_secret_manager_env = false`
- `mongodb_connection_string`
- `google_client_id`

## 2) Create resources

```bash
terraform init
terraform plan
terraform apply
```

After apply, check URL:

```bash
terraform output cloud_run_service_url
```

## 3) Cloud Build: manual GitHub trigger (recommended)

The Terraform `google_cloudbuild_trigger` resource with a legacy `github {}` block often fails with `400 invalid argument` unless you use Cloud Build second-generation repository connections. For a personal project, creating the trigger in the console is simpler.

1. Google Cloud Console → **Cloud Build** → **Triggers** → **Connect repository** (GitHub App).
2. **Create trigger**:
   - Event: Push to a branch (e.g. `^main$`)
   - Source: your repo
   - Configuration: **Cloud Build configuration file** → path `cloudbuild.backend.yaml` (repo root)
   - Included files (optional): `backend/**` and `cloudbuild.backend.yaml`
3. Under **Substitution variables**, add:
   - `_BACKEND_IMAGE` = `asia-northeast1-docker.pkg.dev/daisuke-cafe-search/backend-images/backend`  
   (adjust project/region/repo name if yours differ.)

Terraform already grants the Cloud Build service account `roles/artifactregistry.writer` so pushes to that repository succeed.

One-off build without a trigger:

```bash
gcloud builds submit ./backend --config cloudbuild.backend.yaml
```

(From repo root; ensure `cloudbuild.backend.yaml` paths match your layout.)

When frontend env is updated, use:

- `REACT_APP_BACKEND_ENDPOINT=<cloud_run_service_url>`

## Notes

- `terraform.tfvars` and state files are ignored by `.gitignore`.
- For personal use, `allow_unauthenticated = true` is enabled by default.
- You can tighten access later with IAM and IAP if needed.
- For import-safe operation, runtime service account defaults to the existing Compute default SA. Set `create_runtime_service_account = true` only when you intentionally migrate.
