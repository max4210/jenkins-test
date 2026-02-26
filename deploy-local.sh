#!/usr/bin/env bash
#
# Build (or destroy) the CML lab locally using Terraform — no Jenkins needed.
#
# Usage:
#   ./deploy-local.sh              # validate + create/update lab
#   ./deploy-local.sh destroy      # destroy the lab
#   ./deploy-local.sh plan         # plan only (no changes)
#   ./deploy-local.sh --skip-validation   # skip nac-validate
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ACTION="apply"
SKIP_VALIDATION=false

for arg in "$@"; do
    case "$arg" in
        destroy)           ACTION="destroy" ;;
        plan)              ACTION="plan" ;;
        --skip-validation) SKIP_VALIDATION=true ;;
        *)                 echo "Unknown argument: $arg"; exit 1 ;;
    esac
done

# ── Load .env ────────────────────────────────────────────────────
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "[*] Loading credentials from .env"
    set -a
    # shellcheck disable=SC1090
    source <(grep -v '^\s*#' "$ENV_FILE" | grep '=')
    set +a
else
    echo "[!] No .env file found. Create one with CML_USERNAME, CML_PASSWORD, CML_URL"
fi

CML_URL="${CML_URL:-https://192.168.137.125}"
[[ "$CML_URL" != http* ]] && CML_URL="https://$CML_URL"

DEVICE_USERNAME="${DEVICE_USERNAME:-$CML_USERNAME}"
DEVICE_PASSWORD="${DEVICE_PASSWORD:-$CML_PASSWORD}"

if [ -z "${CML_USERNAME:-}" ] || [ -z "${CML_PASSWORD:-}" ]; then
    echo "[!] CML_USERNAME and CML_PASSWORD must be set"
    exit 1
fi

echo "[*] CML URL:  $CML_URL"
echo "[*] CML User: $CML_USERNAME"
echo ""

# ── Validate YAML ────────────────────────────────────────────────
if [ "$ACTION" != "destroy" ] && [ "$SKIP_VALIDATION" = false ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  Stage: Validate YAML data"
    echo "════════════════════════════════════════════════════════════"

    if command -v nac-validate &>/dev/null; then
        echo "[*] Running schema + rules validation..."
        nac-validate -s "$SCRIPT_DIR/.schema.yaml" -r "$SCRIPT_DIR/.rules" "$SCRIPT_DIR/data/"
        echo "[+] Validation passed."
    else
        echo "[!] nac-validate not found — skipping (pip install nac-validate)"
    fi

    if [ -f "$SCRIPT_DIR/scripts/cross_validate.py" ]; then
        echo "[*] Running cross-file validation..."
        python3 "$SCRIPT_DIR/scripts/cross_validate.py"
        echo "[+] Cross-validation passed."
    fi
    echo ""
fi

# ── Terraform ────────────────────────────────────────────────────
TF_DIR="$SCRIPT_DIR/terraform"

echo "════════════════════════════════════════════════════════════"
echo "  Stage: Terraform ${ACTION^}"
echo "════════════════════════════════════════════════════════════"

export TF_VAR_cml_url="$CML_URL"
export TF_VAR_cml_username="$CML_USERNAME"
export TF_VAR_cml_password="$CML_PASSWORD"
export TF_VAR_device_username="$DEVICE_USERNAME"
export TF_VAR_device_password="$DEVICE_PASSWORD"

cd "$TF_DIR"

echo "[*] terraform init..."
terraform init -input=false

case "$ACTION" in
    destroy)
        echo "[*] terraform destroy..."
        terraform destroy -input=false -auto-approve
        echo "[+] Lab destroyed."
        ;;
    plan)
        echo "[*] terraform plan..."
        terraform plan -input=false
        ;;
    apply)
        echo "[*] terraform plan..."
        terraform plan -input=false -out=tfplan

        echo "[*] terraform apply..."
        terraform apply -input=false tfplan
        rm -f tfplan

        echo ""
        echo "════════════════════════════════════════════════════════════"
        echo "  Lab deployed successfully!"
        echo "════════════════════════════════════════════════════════════"
        terraform output
        ;;
esac
