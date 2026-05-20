"""
辅助工具 - 生成测试卡数据
使用 AWS Payment Cryptography 生成真实的 CVV2 和 PIN 验证值
"""
import boto3
import json

REGION = "ap-southeast-1"
data_client = boto3.client("payment-cryptography-data", region_name=REGION)
control_client = boto3.client("payment-cryptography", region_name=REGION)


def get_key_arn(alias):
    resp = control_client.get_alias(AliasName=f"alias/{alias}")
    return resp["Alias"]["KeyArn"]


def generate_cvv2(pan, expiry_date):
    """为测试卡生成真实 CVV2"""
    key_arn = get_key_arn("poc-issuer-cvk")
    resp = data_client.generate_card_validation_data(
        KeyIdentifier=key_arn,
        PrimaryAccountNumber=pan,
        GenerationAttributes={"CardVerificationValue2": {"CardExpiryDate": expiry_date}},
    )
    return resp["ValidationData"]


def generate_pin_verification_value(pan, encrypted_pin_block):
    """为测试卡生成 PIN 验证值"""
    pek_arn = get_key_arn("poc-issuer-pek")
    pvk_arn = get_key_arn("poc-issuer-pvk")
    resp = data_client.generate_pin_data(
        GenerationKeyIdentifier=pvk_arn,
        EncryptionKeyIdentifier=pek_arn,
        PrimaryAccountNumber=pan,
        PinBlockFormat="ISO_FORMAT_0",
        GenerationAttributes={
            "VisaPin": {"PinVerificationKeyIndex": 1}
        },
        PinDataLength=4,
    )
    return {
        "encrypted_pin_block": resp["EncryptedPinBlock"],
        "pin_verification_value": resp["PinData"]["VerificationValue"],
    }


def generate_test_card_data():
    """生成一张完整测试卡的密码学数据"""
    pan = "5425230000004415"
    expiry = "0127"

    print("🃏 Generating test card cryptographic data...")
    print(f"   PAN: {pan}")
    print(f"   Expiry: {expiry}")
    print()

    # CVV2
    cvv2 = generate_cvv2(pan, expiry)
    print(f"   CVV2: {cvv2}")

    # PIN
    pin_data = generate_pin_verification_value(pan, None)
    print(f"   Encrypted PIN Block: {pin_data['encrypted_pin_block']}")
    print(f"   PIN Verification Value: {pin_data['pin_verification_value']}")

    # 保存测试数据
    test_card = {
        "pan": pan,
        "expiry_date": expiry,
        "cvv2": cvv2,
        "encrypted_pin_block": pin_data["encrypted_pin_block"],
        "pin_verification_value": pin_data["pin_verification_value"],
    }

    output_path = ".state/test_card.json"
    with open(output_path, "w") as f:
        json.dump(test_card, f, indent=2)
    print(f"\n📁 Test card data saved to {output_path}")
    return test_card


if __name__ == "__main__":
    generate_test_card_data()
