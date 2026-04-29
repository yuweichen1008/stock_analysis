#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Oracle — One-time GCP Infrastructure Setup
#
# Run this ONCE before your first deployment.
# After this script completes:
#   1. Fill in the secrets it couldn't auto-generate (see "MANUAL STEPS" at end)
#   2. Replace YOUR_PROJECT_ID in the 4 YAML files
#   3. Run: gcloud builds submit --config cloudbuild.yaml
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── FILL THESE IN BEFORE RUNNING ─────────────────────────────────────────────
PROJECT_ID="YOUR_PROJECT_ID"          # e.g. my-oracle-project-123
REGION="us-central1"
# ─────────────────────────────────────────────────────────────────────────────

if [[ "$PROJECT_ID" == "YOUR_PROJECT_ID" ]]; then
  echo "❌  Edit setup-gcp.sh and set PROJECT_ID before running."
  exit 1
fi

GCS_BUCKET="${PROJECT_ID}-oracle-signals"
DB_INSTANCE="oracle-db"
DB_NAME="oracle"
DB_USER="oracle"
SERVICE_ACCOUNT="oracle-sa"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🚀 Setting up GCP project: ${PROJECT_ID}"
gcloud config set project "$PROJECT_ID"

# ── 1. Enable APIs ─────────────────────────────────────────────────────────────
echo "🔧 Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  sql-component.googleapis.com \
  sqladmin.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com

# ── 2. Artifact Registry ────────────────────────────────────────────────────────
echo "📦 Creating Artifact Registry repo..."
gcloud artifacts repositories create oracle \
  --repository-format=docker \
  --location="$REGION" \
  --description="Oracle Docker images" 2>/dev/null || echo "  (already exists)"

# ── 3. GCS bucket ──────────────────────────────────────────────────────────────
echo "🪣 Creating GCS bucket gs://${GCS_BUCKET}..."
gsutil mb -l "$REGION" "gs://${GCS_BUCKET}" 2>/dev/null || echo "  (already exists)"
gsutil versioning set on "gs://${GCS_BUCKET}"

# ── 4. Cloud SQL ───────────────────────────────────────────────────────────────
echo "🗄️  Creating Cloud SQL instance (this takes ~5 minutes)..."
gcloud sql instances create "$DB_INSTANCE" \
  --database-version=POSTGRES_15 \
  --region="$REGION" \
  --tier=db-f1-micro \
  --storage-size=10GB \
  --storage-type=SSD \
  --backup-start-time=03:00 \
  --availability-type=zonal \
  --no-assign-ip \
  --network=default 2>/dev/null || echo "  (already exists)"

echo "  Creating database and user..."
DB_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | head -c 32)
gcloud sql databases create "$DB_NAME" --instance="$DB_INSTANCE" 2>/dev/null || echo "  (DB already exists)"
gcloud sql users create "$DB_USER" --instance="$DB_INSTANCE" --password="$DB_PASSWORD" 2>/dev/null || \
  DB_PASSWORD="<existing-password-unchanged>"

CONNECTION_NAME="${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
DB_URL="postgresql+psycopg2://${DB_USER}:${DB_PASSWORD}@/oracle?host=/cloudsql/${CONNECTION_NAME}"

# ── 5. Service account ─────────────────────────────────────────────────────────
echo "👤 Creating service account ${SA_EMAIL}..."
gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
  --display-name="Oracle Service Account" 2>/dev/null || echo "  (already exists)"

for ROLE in \
  roles/cloudsql.client \
  roles/storage.objectAdmin \
  roles/secretmanager.secretAccessor \
  roles/run.invoker; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" --quiet
done

# ── 6. Cloud Build service account IAM ────────────────────────────────────────
echo "🔑 Granting Cloud Build SA permissions..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
CB_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

for ROLE in \
  roles/run.admin \
  roles/iam.serviceAccountUser \
  roles/secretmanager.secretAccessor \
  roles/artifactregistry.writer \
  roles/cloudsql.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CB_SA}" \
    --role="$ROLE" --quiet
done

# ── 7. Secrets ─────────────────────────────────────────────────────────────────
echo "🔒 Creating Secret Manager secrets..."

_create_secret() {
  local name="$1"; local value="$2"
  gcloud secrets create "$name" --replication-policy=automatic 2>/dev/null || true
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=-
}

JWT_SECRET=$(openssl rand -base64 48 | tr -d '=+/')
INTERNAL_SECRET=$(openssl rand -base64 48 | tr -d '=+/')

_create_secret "DATABASE_URL"          "$DB_URL"
_create_secret "JWT_SECRET"            "$JWT_SECRET"
_create_secret "INTERNAL_API_SECRET"   "$INTERNAL_SECRET"
_create_secret "GCS_BUCKET"            "$GCS_BUCKET"
_create_secret "ALLOWED_ORIGINS"       "*"
_create_secret "ORACLE_API_BASE"       "https://oracle-api-PLACEHOLDER.a.run.app"

# Placeholder secrets — user must update these manually
for SECRET in TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID GOOGLE_CLIENT_ID ANTHROPIC_API_KEY APPLE_TEAM_ID APPLE_CLIENT_ID; do
  gcloud secrets create "$SECRET" --replication-policy=automatic 2>/dev/null || true
  printf 'PLACEHOLDER' | gcloud secrets versions add "$SECRET" --data-file=- 2>/dev/null || true
done

_create_secret "ORACLE_API_URL"   "https://oracle-api-PLACEHOLDER.a.run.app"
_create_secret "OPTIONS_DRY_RUN"  "false"

# ── 8. Update YAML files with real PROJECT_ID ──────────────────────────────────
echo "📝 Patching YOUR_PROJECT_ID in YAML files..."
for FILE in cloud-run-service.yaml cloud-run-telegram.yaml cloud-run-job-predict.yaml cloud-run-job-resolve.yaml cloud-run-job-news.yaml cloud-run-job-weekly.yaml cloud-run-job-options-screener.yaml; do
  if [[ -f "$FILE" ]]; then
    sed -i.bak "s/YOUR_PROJECT_ID/${PROJECT_ID}/g" "$FILE"
    rm -f "${FILE}.bak"
    echo "  Patched $FILE"
  fi
done

# ── 9. Cloud Scheduler jobs ────────────────────────────────────────────────────
echo "⏰ Creating Cloud Scheduler jobs..."

# Scheduler needs a service account with run.jobs.run permission
SCHEDULER_SA="oracle-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create oracle-scheduler \
  --display-name="Oracle Scheduler" 2>/dev/null || true

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SCHEDULER_SA}" \
  --role="roles/run.developer" --quiet

gcloud scheduler jobs create http oracle-predict \
  --location="$REGION" \
  --schedule="0 8 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-predict:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="Daily TAIEX prediction at 08:00 TST" 2>/dev/null || \
  echo "  oracle-predict scheduler job already exists"

gcloud scheduler jobs create http oracle-resolve \
  --location="$REGION" \
  --schedule="5 14 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-resolve:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="Daily TW pipeline + Oracle resolution at 14:05 TST" 2>/dev/null || \
  echo "  oracle-resolve scheduler job already exists"

gcloud scheduler jobs create http oracle-news-poller-tw \
  --location="$REGION" \
  --schedule="*/30 1-6 * * 1-5" \
  --time-zone="UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-news-poller:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="News poller during TW market hours (09:00–13:30 TST)" 2>/dev/null || \
  echo "  oracle-news-poller-tw scheduler job already exists"

gcloud scheduler jobs create http oracle-news-poller-us \
  --location="$REGION" \
  --schedule="*/30 13-21 * * 1-5" \
  --time-zone="UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-news-poller:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="News poller during US market hours (09:30–17:00 ET)" 2>/dev/null || \
  echo "  oracle-news-poller-us scheduler job already exists"

gcloud scheduler jobs create http oracle-weekly-signals \
  --location="$REGION" \
  --schedule="30 15 * * 1" \
  --time-zone="UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-weekly-signals:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="Weekly ±5% contrarian signals every Monday 10:30 ET" 2>/dev/null || \
  echo "  oracle-weekly-signals scheduler job already exists"

gcloud scheduler jobs create http oracle-options-screener-morning \
  --location="$REGION" \
  --schedule="45 14 * * 1-5" \
  --time-zone="UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-options-screener:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="Options screener 09:45 ET (14:45 UTC) weekdays" 2>/dev/null || \
  echo "  oracle-options-screener-morning scheduler job already exists"

gcloud scheduler jobs create http oracle-options-screener-close \
  --location="$REGION" \
  --schedule="30 20 * * 1-5" \
  --time-zone="UTC" \
  --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/oracle-options-screener:run" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --description="Options screener 15:30 ET (20:30 UTC) weekdays" 2>/dev/null || \
  echo "  oracle-options-screener-close scheduler job already exists"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "✅ GCP setup complete!"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  MANUAL STEPS — fill in these secrets before deploying:"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=- <<< 'your-bot-token'"
echo "  gcloud secrets versions add TELEGRAM_CHAT_ID   --data-file=- <<< 'your-chat-id'"
echo "  gcloud secrets versions add ANTHROPIC_API_KEY  --data-file=- <<< 'sk-ant-...'"
echo "  gcloud secrets versions add GOOGLE_CLIENT_ID   --data-file=- <<< 'your-google-client-id'"
echo ""
echo "  (Apple Sign-In — only if using Apple auth):"
echo "  gcloud secrets versions add APPLE_TEAM_ID      --data-file=- <<< 'your-team-id'"
echo "  gcloud secrets versions add APPLE_CLIENT_ID    --data-file=- <<< 'com.yourco.oracle'"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  AFTER FIRST DEPLOYMENT — update ORACLE_API_BASE + ORACLE_API_URL:"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  gcloud secrets versions add ORACLE_API_BASE --data-file=- <<< 'https://oracle-api-xxxx-uc.a.run.app'"
echo "  gcloud secrets versions add ORACLE_API_URL   --data-file=- <<< 'https://oracle-api-xxxx-uc.a.run.app'"
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  DEPLOY:"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  gcloud builds submit --config cloudbuild.yaml"
echo ""
echo "  Cloud SQL connection: ${CONNECTION_NAME}"
echo "  GCS bucket:          gs://${GCS_BUCKET}"
echo ""
