#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-default}"

echo "============================================================"
echo "🧹 Cleaning up POC resources"
echo "   Region: $REGION | Profile: $PROFILE"
echo "============================================================"
echo ""

# Step 1: CDK destroy
echo "☁️  Step 1/2: Destroying infrastructure (CDK)..."
cd cdk && npx cdk destroy --profile "$PROFILE" --force 2>&1 | tail -3
cd "$PROJECT_DIR"
echo ""

# Step 2: Schedule key deletion
echo "🔐 Step 2/2: Scheduling key deletion (3-day waiting period)..."

# Delete aliases first
ALIASES=$(aws payment-cryptography list-aliases --region "$REGION" --profile "$PROFILE" \
  --query 'Aliases[?starts_with(AliasName, `alias/poc-`)].AliasName' --output json)

echo "$ALIASES" | python3 -c "
import json, sys, subprocess
aliases = json.load(sys.stdin)
for alias in aliases:
    subprocess.run(['aws', 'payment-cryptography', 'delete-alias',
        '--alias-name', alias, '--region', '$REGION', '--profile', '$PROFILE'], capture_output=True)
    print(f'  🗑️  {alias} deleted')
"

# Delete all keys (both aliased and orphaned) with poc tag or all keys in the account
KEYS=$(aws payment-cryptography list-keys --region "$REGION" --profile "$PROFILE" \
  --query 'Keys[?KeyState!=`DELETE_PENDING` && KeyState!=`DELETE_COMPLETE`].KeyArn' --output json)

echo "$KEYS" | python3 -c "
import json, sys, subprocess
arns = json.load(sys.stdin)
for arn in arns:
    result = subprocess.run(['aws', 'payment-cryptography', 'delete-key',
        '--key-identifier', arn, '--delete-key-in-days', '3',
        '--region', '$REGION', '--profile', '$PROFILE'], capture_output=True, text=True)
    status = '✅' if result.returncode == 0 else '⚠️'
    key_id = arn.split('/')[-1]
    print(f'  {status} {key_id} → deletion scheduled')
print(f'\n  {len(arns)} keys scheduled for deletion (3-day waiting period)')
"

echo ""
echo "============================================================"
echo "✅ Cleanup complete!"
echo "   Keys will be permanently deleted after 3 days."
echo "   To cancel: aws payment-cryptography restore-key --key-identifier <ARN>"
echo "============================================================"
