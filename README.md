# POC: Issuer on Mastercard Cloud Edge with AWS Payment Cryptography

## 场景

模拟香港发卡方（Issuer）通过 Mastercard Cloud Edge 接入支付网络，使用 AWS Payment Cryptography 替代传统物理 HSM 完成支付交易授权。

**参考新闻**：[Mastercard 透過 Cloud Edge 平台將客戶涵接其支付網絡時間縮短四倍](https://www.mastercard.com/news/ap/zh-hk/新聞中心/新聞發佈/zh-hk/2025/mastercard透過cloud-edge平台將客戶涵接其支付網絡時間縮短四倍/)

## 技术栈

- Python 3.13 + uv
- AWS Payment Cryptography（支付 HSM）
- AWS Lambda + API Gateway（Issuer Host）
- AWS CDK（IaC）
- Region: ap-southeast-1

## 快速开始

```bash
# 一键部署（安装依赖 → CDK 部署 → 初始化密钥 → 生成测试数据 → 写入 .env）
export AWS_PROFILE=<your-profile>  # 可选，默认使用 default profile
./deploy.sh

# 运行演示
uv run python3 demo/simulate_transactions.py

# 通过 API 调用
source .env
curl -s -X POST "$API_URL/authorize" \
  -H "Content-Type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d '{"transaction_type":"ecommerce","pan":"5425230000004415","amount":299,"currency":"HKD","expiry_date":"0127","cvv2":"683"}'
```

## 演示场景

| # | 场景 | 密码学操作 | 预期结果 |
|---|------|-----------|---------|
| 1 | 电商购物（正确 CVV） | CVV2 验证 | ✅ Approved |
| 2 | 欺诈尝试（错误 CVV） | CVV2 验证 | ❌ Declined |
| 3 | ATM 取款（正确 PIN） | PIN 验证 | ✅ Approved |
| 4 | EMV 芯片卡 POS | ARQC 验证 | ❌ Declined（模拟值） |

## 文档

- [演示指南](docs/presentation.md) — 完整演示步骤和讲解要点
- [架构详情](README.md) — 本文件

## 安全措施

- API Gateway 启用 API Key 认证
- Usage Plan 限速（10 req/s，1000 req/day）
- Lambda IAM 最小权限（仅 Verify 操作）
- 密钥存储在 PCI PIN 认证的 AWS 托管 HSM 中
- `.env` 已加入 `.gitignore`

## 清理资源

```bash
cd cdk && npx cdk destroy --profile lab
AWS_PROFILE=lab aws payment-cryptography list-aliases --region ap-southeast-1
# 手动删除密钥（密钥有 7 天删除等待期）
```
