#!/usr/bin/env bash
set -euo pipefail

# POC 一键部署脚本
# 完成后自动生成 .env 和 .state/ 中的运行时数据

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-default}"

echo "============================================================"
echo "🚀 Deploying POC: Mastercard Cloud Edge + AWS Payment Cryptography"
echo "   Region: $REGION | Profile: $PROFILE"
echo "============================================================"
echo ""

# Step 1: 安装依赖
echo "📦 Step 1/4: Installing dependencies..."
uv sync --quiet
echo ""

# Step 2: CDK 部署
echo "☁️  Step 2/4: Deploying infrastructure (CDK)..."
cd cdk
npx cdk deploy --profile "$PROFILE" --require-approval never --outputs-file "$PROJECT_DIR/.state/cdk-outputs.json" 2>&1 | grep -E "✅|Total|error|failed" || true
cd "$PROJECT_DIR"
echo ""

# 从 CDK outputs 中提取值
API_URL=$(python3 -c "import json; d=json.load(open('.state/cdk-outputs.json')); print(d['poc-mastercard-cloud-edge']['ApiUrl'])" 2>/dev/null || echo "")
API_KEY_ID=$(python3 -c "import json; d=json.load(open('.state/cdk-outputs.json')); print(d['poc-mastercard-cloud-edge']['ApiKeyId'])" 2>/dev/null || echo "")

if [ -z "$API_URL" ] || [ -z "$API_KEY_ID" ]; then
  echo "❌ Failed to extract CDK outputs. Check deployment logs."
  exit 1
fi

# 获取 API Key 值
API_KEY=$(aws apigateway get-api-key --api-key "$API_KEY_ID" --include-value --profile "$PROFILE" --region "$REGION" --query 'value' --output text)

# 写入 .env
cat > .env <<EOF
API_URL=${API_URL}
API_KEY=${API_KEY}
AWS_REGION=${REGION}
AWS_PROFILE=${PROFILE}
EOF
echo "📝 .env updated"

# 生成前端配置
cat > docs/config.js <<JSEOF
// Auto-generated from deploy.sh - do not commit
const CONFIG = {
  apiUrl: '${API_URL}',
  apiKey: '${API_KEY}'
};
JSEOF
echo "📝 docs/config.js updated"

# Step 3: 初始化密钥
echo ""
echo "🔐 Step 3/4: Setting up payment keys..."
mkdir -p .state
AWS_PROFILE="$PROFILE" uv run python3 src/key_management/setup_keys.py
echo ""

# Step 4: 生成测试卡数据
echo "🃏 Step 4/4: Generating test card data..."
AWS_PROFILE="$PROFILE" uv run python3 src/key_management/generate_test_data.py
echo ""

echo "============================================================"
echo "✅ Deployment complete!"
echo ""
echo "   API URL:  $API_URL"
echo "   API Key:  ${API_KEY:0:8}...${API_KEY: -4}"
echo ""
echo "   Run demo: AWS_PROFILE=$PROFILE uv run python3 demo/simulate_transactions.py"
echo "   Or:       source .env && curl -s -X POST \"\$API_URL/authorize\" \\"
echo "             -H \"x-api-key: \$API_KEY\" -H \"Content-Type: application/json\" \\"
echo "             -d '{\"transaction_type\":\"ecommerce\",\"pan\":\"5425230000004415\",\"amount\":299,\"currency\":\"HKD\",\"expiry_date\":\"0127\",\"cvv2\":\"683\"}'"
echo "============================================================"
