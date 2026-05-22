"""
发卡方密钥初始化脚本
在 AWS Payment Cryptography 中创建 Issuer 所需的密钥体系
"""
import boto3
import json

REGION = "ap-southeast-1"
client = boto3.client("payment-cryptography", region_name=REGION)


def create_key(alias, key_usage, key_algorithm="TDES_2KEY", modes_of_use=None):
    """创建密钥并打印结果"""
    if modes_of_use is None:
        modes_of_use = {"Generate": True, "Verify": True}

    # 先检查别名是否已存在
    try:
        alias_resp = client.get_alias(AliasName=f"alias/{alias}")
        print(f"⏭️  {alias} already exists: {alias_resp['Alias']['KeyArn']}")
        print()
        return alias_resp["Alias"]["KeyArn"]
    except client.exceptions.ResourceNotFoundException:
        pass

    resp = client.create_key(
        Exportable=True,
        KeyAttributes={
            "KeyAlgorithm": key_algorithm,
            "KeyUsage": key_usage,
            "KeyClass": "SYMMETRIC_KEY",
            "KeyModesOfUse": modes_of_use,
        },
        Tags=[{"Key": "Project", "Value": "poc-mastercard-cloud-edge"}],
    )
    key = resp["Key"]
    print(f"✅ Created {alias}")
    print(f"   ARN: {key['KeyArn']}")
    print(f"   KCV: {key['KeyCheckValue']}")
    print()

    client.create_alias(AliasName=f"alias/{alias}", KeyArn=key["KeyArn"])
    return key["KeyArn"]


def setup_issuer_keys():
    """创建发卡方完整密钥体系"""
    print("=" * 60)
    print("🔐 Setting up Issuer Key Hierarchy")
    print(f"   Region: {REGION}")
    print("=" * 60)
    print()

    keys = {}

    # 1. CVK - Card Verification Key (CVV/CVV2)
    keys["cvk"] = create_key(
        alias="poc-issuer-cvk",
        key_usage="TR31_C0_CARD_VERIFICATION_KEY",
    )

    # 2. PVK - PIN Verification Key
    keys["pvk"] = create_key(
        alias="poc-issuer-pvk",
        key_usage="TR31_V2_VISA_PIN_VERIFICATION_KEY",
    )

    # 3. IMK-AC - Issuer Master Key for Application Cryptograms (ARQC/ARPC)
    keys["imk_ac"] = create_key(
        alias="poc-issuer-imk-ac",
        key_usage="TR31_E0_EMV_MKEY_APP_CRYPTOGRAMS",
        modes_of_use={"DeriveKey": True},
    )

    # 4. PEK - PIN Encryption Key (for PIN block decryption)
    keys["pek"] = create_key(
        alias="poc-issuer-pek",
        key_usage="TR31_P0_PIN_ENCRYPTION_KEY",
        modes_of_use={"Encrypt": True, "Decrypt": True, "Wrap": True, "Unwrap": True},
    )

    # 5. dCVV2 IMK - Issuer Master Key for Dynamic CVV2
    keys["dcvv2_imk"] = create_key(
        alias="poc-issuer-dcvv2-imk",
        key_usage="TR31_E6_EMV_MKEY_OTHER",
        modes_of_use={"DeriveKey": True},
    )

    # 6. Acquirer PEK - 收单方 PIN 加密密钥（模拟）
    keys["acquirer_pek"] = create_key(
        alias="poc-acquirer-pek",
        key_usage="TR31_P0_PIN_ENCRYPTION_KEY",
        modes_of_use={"Encrypt": True, "Decrypt": True, "Wrap": True, "Unwrap": True},
    )

    # 7. MAC Key - 交易消息认证密钥
    keys["mac_key"] = create_key(
        alias="poc-mac-key",
        key_usage="TR31_M1_ISO_9797_1_MAC_KEY",
    )

    # 8. Data Encryption Key - 敏感数据加密
    keys["data_encrypt_key"] = create_key(
        alias="poc-data-encrypt-key",
        key_usage="TR31_D0_SYMMETRIC_DATA_ENCRYPTION_KEY",
        modes_of_use={"Encrypt": True, "Decrypt": True, "Wrap": True, "Unwrap": True},
    )

    # 9. KEK - Key Encryption Key（用于 TR-31 密钥导出/导入）
    keys["kek"] = create_key(
        alias="poc-kek",
        key_usage="TR31_K0_KEY_ENCRYPTION_KEY",
        modes_of_use={"Encrypt": True, "Decrypt": True, "Wrap": True, "Unwrap": True},
    )

    # 保存密钥 ARN 映射
    output_path = ".state/key_arns.json"
    with open(output_path, "w") as f:
        json.dump(keys, f, indent=2)
    print(f"📁 Key ARNs saved to {output_path}")
    print()
    print("✅ Issuer key setup complete!")


if __name__ == "__main__":
    setup_issuer_keys()
