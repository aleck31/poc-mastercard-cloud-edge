# POC: Issuer on Mastercard Cloud Edge with AWS Payment Cryptography

## 场景

模拟发卡方（Issuer）通过 Mastercard Cloud Edge 接入支付网络，使用 AWS Payment Cryptography 替代传统物理 HSM 完成支付交易授权。

---

自研 Card Processor 需要解决两个最重的基础设施问题：**加密机**和**卡组织网络接入**。本 POC 验证了在 AWS 上用云原生方案替代传统硬件的技术可行性。

| 传统方案 | 本 POC 验证的云方案 |
|---------|-------------------|
| 采购物理 HSM（Thales payShield 等），$50K-100K + 数月交付 | AWS Payment Cryptography，API 调用即用，按量计费 |
| 物理机房 + 专线接入卡组织 | Mastercard Cloud Edge + AWS PrivateLink |
| HSM 固件维护、密钥仪式需人工 | 全托管，PCI PIN/P2PE 已认证 |
| 扩容需采购硬件，周期 3-6 个月 | 自动弹性伸缩 |

## 验证的核心能力

本 POC 通过 **真实调用** AWS Payment Cryptography API，演示了 Card Processor 密码学操作：

| 操作 | 说明 | 状态 |
|------|------|------|
| CVV/CVV2 生成与验证 | 卡片验证值 | ✅ 已验证 |
| dCVV2 动态验证 | 动态卡验证值，防重放攻击 | ✅ 已验证 |
| PIN 验证 | ATM/POS PIN 校验 | ✅ 已验证 |
| ARQC/ARPC 验证 | EMV 芯片卡交易认证 | ✅ 已验证 |
| 密钥创建与管理 | TR-31 Key Block 创建 | ✅ 已验证 |
| PIN 翻译（PIN Translate） | 收单方 → 发卡方密钥转换 | ✅ 已验证 |
| PIN Block 重加密 | 不同格式/密钥间转换 | ✅ 已验证 |
| MAC 生成与验证 | 交易消息完整性认证 | ✅ 已验证 |
| 数据加密/解密 | 敏感字段加密（如 PAN） | ✅ 已验证 |
| 密钥交换（TR-31/TR-34） | 与卡组织/收单方密钥分发 | ✅ 已验证 |
| 卡片个人化密钥派生 | 发卡时为每张卡派生唯一密钥 | 🔲 支持，未演示 |
| 3D Secure（CAVV） | 在线交易额外认证 | 🔲 支持，未演示 |

## 生产化路径

本 POC 使用 Serverless 架构（Lambda + API Gateway）快速验证。生产环境大规模交易处理建议演进为：

```
                POC 架构                          生产架构
         (验证密码学可行性)                   (高性能低延迟)

API Gateway → Lambda                NLB → ECS/EKS (常驻容器)
      │                                    │
      ▼                                    ▼
Payment Cryptography              Payment Cryptography (不变)
```

生产架构调整点：
- **计算层**：Lambda → ECS/EKS 常驻容器（消除冷启动，支持长连接）
- **网络层**：API Gateway → NLB（四层负载，更低延迟）
- **连接方式**：HTTPS → PrivateLink / Direct Connect（与卡组织持久连接）
- **加密机层**：无需变更，Payment Cryptography API 调用方式完全相同

**结论：加密机层的验证结果可直接复用到生产架构。**

## 快速开始

```bash
# 一键部署
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

## 交互式演示

部署完成后打开 [docs/presentation.html](docs/presentation.html)，在浏览器中直接点击按钮即可实时调用 API 查看结果。

## 技术栈

- Python 3.13 + uv
- AWS Payment Cryptography（支付 HSM）
- AWS Lambda + API Gateway（POC 演示用）
- AWS CDK（IaC）
- Region: ap-southeast-1

## 安全措施

- API Gateway 启用 API Key 认证 + 速率限制（10 req/s）
- Lambda IAM 最小权限（仅允许 Verify 操作）
- 密钥存储在 PCI PIN 认证的 AWS 托管 HSM 中

## 清理资源

```bash
cd cdk && npx cdk destroy
aws payment-cryptography list-aliases --region ap-southeast-1
# 手动删除密钥（密钥有 7 天删除等待期）
```
