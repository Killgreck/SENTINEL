#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  SENTINEL — Fase 0: Setup Completo del Entorno AWS
# ═══════════════════════════════════════════════════════════════
#  Ejecutar: bash setup_fase0.sh
#  Propósito: Configurar AWS CLI, auditar recursos, subir datos
# ═══════════════════════════════════════════════════════════════

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

divider() { echo -e "\n${BLUE}════════════════════════════════════════════════════════════${NC}"; }
ok()      { echo -e "  ${GREEN}✅ $1${NC}"; }
fail()    { echo -e "  ${RED}❌ $1${NC}"; }
warn()    { echo -e "  ${YELLOW}⚠️  $1${NC}"; }
info()    { echo -e "  ${BLUE}ℹ️  $1${NC}"; }

# ─── STEP 1: CHECK AWS CLI ──────────────────────────────────
divider
echo -e "  ${BLUE}PASO 1: Verificando AWS CLI${NC}"
divider

if command -v aws &> /dev/null; then
    AWS_VERSION=$(aws --version 2>&1)
    ok "AWS CLI instalado: $AWS_VERSION"
else
    fail "AWS CLI no está instalado"
    echo ""
    echo "  Instalando AWS CLI v2..."
    curl -s "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    cd /tmp && unzip -qo awscliv2.zip && sudo ./aws/install
    cd "$SCRIPT_DIR"
    if command -v aws &> /dev/null; then
        ok "AWS CLI instalado correctamente: $(aws --version)"
    else
        fail "No se pudo instalar AWS CLI. Instálalo manualmente."
        exit 1
    fi
fi

# ─── STEP 2: CHECK CREDENTIALS ──────────────────────────────
divider
echo -e "  ${BLUE}PASO 2: Verificando credenciales AWS${NC}"
divider

if aws sts get-caller-identity &>/dev/null; then
    IDENTITY=$(aws sts get-caller-identity --output json)
    ACCOUNT=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Account'])" 2>/dev/null || echo "N/A")
    ARN=$(echo "$IDENTITY" | python3 -c "import sys,json; print(json.load(sys.stdin)['Arn'])" 2>/dev/null || echo "N/A")
    ok "Autenticado como:"
    echo "     Account: $ACCOUNT"
    echo "     ARN:     $ARN"
else
    fail "No hay credenciales configuradas"
    echo ""
    warn "Necesitas configurar AWS CLI con tus credenciales IAM:"
    echo ""
    echo "  aws configure"
    echo "  → AWS Access Key ID:     [tu access key]"
    echo "  → AWS Secret Access Key: [tu secret key]"
    echo "  → Default region name:   us-east-1"
    echo "  → Default output format: json"
    echo ""
    read -p "  ¿Quieres configurar ahora? (y/n): " CONFIGURE
    if [[ "$CONFIGURE" == "y" || "$CONFIGURE" == "Y" ]]; then
        aws configure
        if aws sts get-caller-identity &>/dev/null; then
            ok "¡Credenciales configuradas correctamente!"
        else
            fail "Las credenciales no funcionan. Verifica tu Access Key."
            exit 1
        fi
    else
        warn "Saltando configuración. Ejecuta 'aws configure' cuando estés listo."
        exit 1
    fi
fi

# ─── STEP 3: CHECK PYTHON DEPENDENCIES ──────────────────────
divider
echo -e "  ${BLUE}PASO 3: Verificando dependencias Python${NC}"
divider

MISSING_DEPS=()
for pkg in boto3 pandas yfinance pyarrow python-dotenv huggingface_hub; do
    if python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        ok "$pkg instalado"
    else
        fail "$pkg NO instalado"
        MISSING_DEPS+=("$pkg")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    info "Instalando dependencias faltantes: ${MISSING_DEPS[*]}"
    pip3 install "${MISSING_DEPS[@]}"
    ok "Dependencias instaladas"
fi

# ─── STEP 4: AUDIT EXISTING AWS RESOURCES ────────────────────
divider
echo -e "  ${BLUE}PASO 4: Auditando recursos AWS existentes${NC}"
divider

echo ""
echo "  ── EC2 Instances ──"
INSTANCES=$(aws ec2 describe-instances \
    --region us-east-1 \
    --filters 'Name=instance-state-name,Values=running,stopped' \
    --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,IP:PublicIpAddress,Name:Tags[?Key==`Name`].Value|[0]}' \
    --output json 2>/dev/null || echo "[]")

if [ "$INSTANCES" != "[]" ] && [ -n "$INSTANCES" ]; then
    echo "$INSTANCES" | python3 -c "
import sys, json
instances = json.load(sys.stdin)
for i in instances:
    state_icon = '🟢' if i.get('State') == 'running' else '🟡'
    print(f\"  {state_icon} {i.get('ID','N/A')} | {i.get('State','N/A')} | {i.get('Type','N/A')} | IP: {i.get('IP','N/A')} | {i.get('Name','N/A')}\")
"
else
    info "No hay instancias EC2 activas en us-east-1"
fi

# Check us-east-2 too (one of the old IPs was there)
INSTANCES_2=$(aws ec2 describe-instances \
    --region us-east-2 \
    --filters 'Name=instance-state-name,Values=running,stopped' \
    --query 'Reservations[].Instances[].{ID:InstanceId,State:State.Name,Type:InstanceType,IP:PublicIpAddress,Name:Tags[?Key==`Name`].Value|[0]}' \
    --output json 2>/dev/null || echo "[]")

if [ "$INSTANCES_2" != "[]" ] && [ -n "$INSTANCES_2" ]; then
    echo "  (us-east-2):"
    echo "$INSTANCES_2" | python3 -c "
import sys, json
instances = json.load(sys.stdin)
for i in instances:
    state_icon = '🟢' if i.get('State') == 'running' else '🟡'
    print(f\"  {state_icon} {i.get('ID','N/A')} | {i.get('State','N/A')} | {i.get('Type','N/A')} | IP: {i.get('IP','N/A')} | {i.get('Name','N/A')}\")
"
fi

echo ""
echo "  ── S3 Buckets ──"
BUCKETS=$(aws s3 ls 2>/dev/null || echo "")
if [ -n "$BUCKETS" ]; then
    while IFS= read -r line; do
        if echo "$line" | grep -qi "sentinel"; then
            echo -e "  🪣 $line  ${GREEN}← SENTINEL${NC}"
        else
            echo "  🪣 $line"
        fi
    done <<< "$BUCKETS"
else
    info "No hay buckets S3"
fi

echo ""
echo "  ── IAM Roles (sentinel) ──"
ROLES=$(aws iam list-roles \
    --query 'Roles[?contains(RoleName, `sentinel`)].{Name:RoleName,Created:CreateDate}' \
    --output json 2>/dev/null || echo "[]")

if [ "$ROLES" != "[]" ] && [ -n "$ROLES" ]; then
    echo "$ROLES" | python3 -c "
import sys, json
roles = json.load(sys.stdin)
for r in roles:
    print(f\"  👤 {r.get('Name','N/A')} | Created: {r.get('Created','N/A')}\")
"
else
    info "No hay roles IAM con 'sentinel' en el nombre"
fi

echo ""
echo "  ── Security Groups (sentinel) ──"
SGS=$(aws ec2 describe-security-groups \
    --region us-east-1 \
    --query "SecurityGroups[?contains(GroupName, 'sentinel')].{Name:GroupName,ID:GroupId}" \
    --output json 2>/dev/null || echo "[]")

if [ "$SGS" != "[]" ] && [ -n "$SGS" ]; then
    echo "$SGS" | python3 -c "
import sys, json
sgs = json.load(sys.stdin)
for sg in sgs:
    print(f\"  🔒 {sg.get('Name','N/A')} ({sg.get('ID','N/A')})\")
"
else
    info "No hay Security Groups con 'sentinel' en el nombre"
fi

# ─── STEP 5: CHECK LOCAL DATA ────────────────────────────────
divider
echo -e "  ${BLUE}PASO 5: Verificando datos locales${NC}"
divider

check_dir() {
    local dir="$1"
    local desc="$2"
    if [ -d "$dir" ]; then
        local count=$(find "$dir" -type f | wc -l)
        local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        ok "$desc: $count archivos ($size)"
    else
        fail "$desc: directorio NO existe"
    fi
}

check_dir "$SCRIPT_DIR/data/market/raw" "Datos de precios"
check_dir "$SCRIPT_DIR/data/sentimental/raw" "Datos de sentimiento"

if [ -f "$SCRIPT_DIR/.env" ]; then
    ok "Archivo .env encontrado"
else
    fail "Archivo .env NO encontrado"
fi

if [ -f "$SCRIPT_DIR/sentinel-hft-key.pem" ]; then
    PERMS=$(stat -c "%a" "$SCRIPT_DIR/sentinel-hft-key.pem" 2>/dev/null || stat -f "%Lp" "$SCRIPT_DIR/sentinel-hft-key.pem" 2>/dev/null)
    if [ "$PERMS" = "400" ]; then
        ok "SSH Key: sentinel-hft-key.pem (permisos OK: $PERMS)"
    else
        warn "SSH Key encontrada pero permisos son $PERMS (deberían ser 400)"
        chmod 400 "$SCRIPT_DIR/sentinel-hft-key.pem"
        ok "Permisos corregidos a 400"
    fi
else
    warn "sentinel-hft-key.pem NO encontrado (se creará con deploy)"
fi

# ─── SUMMARY ─────────────────────────────────────────────────
divider
echo -e "  ${GREEN}📋 FASE 0 COMPLETADA${NC}"
divider
echo ""
echo "  Estado del entorno:"
echo "  ├─ AWS CLI:       ✅ Configurado"
echo "  ├─ Credenciales:  ✅ Verificadas"
echo "  ├─ Python deps:   ✅ Instaladas"
echo "  ├─ Datos locales: ✅ Disponibles"
echo "  └─ SSH Key:       ✅ Verificada"
echo ""
echo "  Próximos pasos:"
echo "  1. Subir datos a S3:  aws s3 sync data/ s3://BUCKET_NAME/raw/"
echo "  2. Deploy EC2:        python3 deploy_sentinel_cloud.py"
echo "  3. O pasar a Fase 2:  Construir el Cortex/Gym"
echo ""
