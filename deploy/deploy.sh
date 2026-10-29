#!/usr/bin/env bash
# Déploie (ou met à jour) automatic-youtube-downloader sur Google Cloud.
# Relançable sans risque : chaque étape vérifie si la ressource existe déjà.
#
# Usage : ./deploy/deploy.sh [config.env]
set -euo pipefail

cd "$(dirname "$0")/.."

info() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mErreur : %s\033[0m\n' "$*" >&2; exit 1; }

# Réessaie une commande (les comptes de service fraîchement créés mettent quelques secondes à exister).
retry() {
  local attempt
  for attempt in 1 2 3 4 5 6; do
    "$@" && return 0
    echo "  ...nouvel essai dans 10 s ($attempt/6)"
    sleep 10
  done
  return 1
}

# --- Configuration ---------------------------------------------------------------------------

CONFIG_FILE="${1:-config.env}"
[[ -f "$CONFIG_FILE" ]] || die "$CONFIG_FILE introuvable. Copie config.example.env en config.env et remplis-le."

while IFS='=' read -r key value || [[ -n "$key" ]]; do
  key="${key%$'\r'}"; value="${value%$'\r'}"
  [[ -z "$key" || "$key" == \#* ]] && continue
  export "$key=$value"
done < "$CONFIG_FILE"

: "${PROJECT_ID:?PROJECT_ID manquant dans $CONFIG_FILE}"
: "${PLAYLISTS:?PLAYLISTS manquant dans $CONFIG_FILE}"
REGION="${REGION:-europe-west1}"
DRIVE_FOLDER_NAME="${DRIVE_FOLDER_NAME:-DJ - YouTube}"
SCHEDULE="${SCHEDULE:-0 6 * * *}"
TIME_ZONE="${TIME_ZONE:-Europe/Paris}"
AUDIO_BITRATE="${AUDIO_BITRATE:-320}"
MAX_DOWNLOADS_PER_RUN="${MAX_DOWNLOADS_PER_RUN:-0}"
TOKEN_FILE="${TOKEN_FILE:-token.json}"
COOKIES_FILE="${COOKIES_FILE:-cookies.txt}"

[[ -f "$TOKEN_FILE" ]] || die "$TOKEN_FILE introuvable. Lance d'abord : python scripts/get_drive_token.py client_secret.json"

NAME="automatic-youtube-downloader"
SHORT="ytdl"  # préfixe court : les comptes de service GCP sont limités à 30 caractères
BUCKET="${PROJECT_ID}-${SHORT}-state"
RUNNER_SA="${SHORT}-runner@${PROJECT_ID}.iam.gserviceaccount.com"
SCHEDULER_SA="${SHORT}-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${NAME}/${NAME}:$(date +%Y%m%d-%H%M%S)"

# Compte et projet valables uniquement pour ce script : la config gcloud globale n'est pas modifiée.
export CLOUDSDK_CORE_PROJECT="$PROJECT_ID"
if [[ -n "${GCLOUD_ACCOUNT:-}" ]]; then
  gcloud auth list --format='value(account)' 2>/dev/null | grep -qx "$GCLOUD_ACCOUNT" \
    || die "$GCLOUD_ACCOUNT n'est pas connecté à gcloud. Lance d'abord : gcloud auth login $GCLOUD_ACCOUNT"
  export CLOUDSDK_CORE_ACCOUNT="$GCLOUD_ACCOUNT"
fi

# --- Prérequis -------------------------------------------------------------------------------

info "Compte $(gcloud config get-value account 2>/dev/null), projet $PROJECT_ID"
BILLING_ENABLED="$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingEnabled)')" \
  || die "Ce compte n'a pas accès au projet $PROJECT_ID. Renseigne le bon compte dans GCLOUD_ACCOUNT (config.env)."
[[ "$BILLING_ENABLED" == "True" ]] || die "Aucun compte de facturation lié au projet. Voir le README, étape 1."

info "Activation des APIs (peut prendre une minute)"
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com \
  artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com \
  drive.googleapis.com iam.googleapis.com

# --- Comptes de service ----------------------------------------------------------------------

info "Comptes de service"
for sa in runner scheduler; do
  gcloud iam service-accounts describe "${SHORT}-${sa}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "${SHORT}-${sa}" --display-name="${NAME} ${sa}"
done

# Cloud Build utilise le compte Compute par défaut : on s'assure qu'il peut construire et pousser l'image.
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BUILD_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  retry gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${BUILD_SA}" \
    --role="$role" --condition=None >/dev/null
done

# --- Stockage --------------------------------------------------------------------------------

info "Bucket d'état gs://${BUCKET}"
gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 \
  || gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access
retry gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${RUNNER_SA}" --role=roles/storage.objectAdmin >/dev/null

info "Dépôt d'images Artifact Registry"
if ! gcloud artifacts repositories describe "$NAME" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$NAME" --repository-format=docker --location="$REGION"
fi
# Ne garde que les 2 dernières images pour rester sous les 0,5 Go gratuits.
POLICY_FILE="$(mktemp)"
cat > "$POLICY_FILE" <<'JSON'
[
  {"name": "delete-old", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}},
  {"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$NAME" --location="$REGION" \
  --policy="$POLICY_FILE" --no-dry-run >/dev/null \
  || echo "  (politique de nettoyage non appliquée, sans gravité)"
rm -f "$POLICY_FILE"

# --- Secrets ---------------------------------------------------------------------------------

# Crée le secret ou ajoute une version si le contenu a changé.
upsert_secret() {
  local name="$1" file="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    if [[ "$(gcloud secrets versions access latest --secret="$name" 2>/dev/null || true)" != "$(cat "$file")" ]]; then
      gcloud secrets versions add "$name" --data-file="$file" >/dev/null
      echo "  $name : nouvelle version"
    else
      echo "  $name : inchangé"
    fi
  else
    gcloud secrets create "$name" --replication-policy=automatic --data-file="$file" >/dev/null
    echo "  $name : créé"
  fi
  retry gcloud secrets add-iam-policy-binding "$name" --member="serviceAccount:${RUNNER_SA}" \
    --role=roles/secretmanager.secretAccessor >/dev/null
}

info "Secrets"
SECRETS="DRIVE_TOKEN_JSON=${NAME}-drive-token:latest"
upsert_secret "${NAME}-drive-token" "$TOKEN_FILE"

if [[ -f "$COOKIES_FILE" ]]; then
  upsert_secret "${NAME}-yt-cookies" "$COOKIES_FILE"
  SECRETS+=",YT_COOKIES=${NAME}-yt-cookies:latest"
fi

if [[ -n "${PROXY_URL:-}" ]]; then
  PROXY_TMP="$(mktemp)"
  printf '%s' "$PROXY_URL" > "$PROXY_TMP"
  upsert_secret "${NAME}-proxy" "$PROXY_TMP"
  rm -f "$PROXY_TMP"
  SECRETS+=",PROXY_URL=${NAME}-proxy:latest"
fi

# --- Image et job ----------------------------------------------------------------------------

info "Construction de l'image (Cloud Build, ~3 min)"
gcloud builds submit --tag "$IMAGE" .

yaml_escape() { local v="${1//\\/\\\\}"; printf '"%s"' "${v//\"/\\\"}"; }
ENV_FILE="$(mktemp)"
{
  echo "PLAYLISTS: $(yaml_escape "$PLAYLISTS")"
  echo "DRIVE_FOLDER_NAME: $(yaml_escape "$DRIVE_FOLDER_NAME")"
  echo "STATE_URI: $(yaml_escape "gs://${BUCKET}/state.json")"
  echo "AUDIO_BITRATE: $(yaml_escape "$AUDIO_BITRATE")"
  echo "MAX_DOWNLOADS_PER_RUN: $(yaml_escape "$MAX_DOWNLOADS_PER_RUN")"
} > "$ENV_FILE"

info "Déploiement du Cloud Run Job"
gcloud run jobs deploy "$NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUNNER_SA" \
  --tasks=1 --max-retries=0 --task-timeout=6h \
  --cpu=1 --memory=2Gi \
  --env-vars-file="$ENV_FILE" \
  --set-secrets="$SECRETS"
rm -f "$ENV_FILE"

retry gcloud run jobs add-iam-policy-binding "$NAME" --region="$REGION" \
  --member="serviceAccount:${SCHEDULER_SA}" --role=roles/run.invoker >/dev/null

# --- Planification ---------------------------------------------------------------------------

info "Planification quotidienne (${SCHEDULE}, ${TIME_ZONE})"
RUN_URI="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${NAME}:run"
SCHEDULER_ARGS=(--location="$REGION" --schedule="$SCHEDULE" --time-zone="$TIME_ZONE"
  --uri="$RUN_URI" --http-method=POST --oauth-service-account-email="$SCHEDULER_SA")
if gcloud scheduler jobs describe "${NAME}-daily" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${NAME}-daily" "${SCHEDULER_ARGS[@]}" >/dev/null
else
  gcloud scheduler jobs create http "${NAME}-daily" "${SCHEDULER_ARGS[@]}" >/dev/null
fi

info "Terminé !"
cat <<EOF
Lancer un run maintenant :
  gcloud run jobs execute ${NAME} --region=${REGION}

Voir les logs :
  https://console.cloud.google.com/run/jobs/details/${REGION}/${NAME}/executions?project=${PROJECT_ID}
EOF
