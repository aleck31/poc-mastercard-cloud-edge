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

    # dCVV2
    key_arn = get_key_arn("poc-issuer-dcvv2-imk")
    dcvv2_resp = data_client.generate_card_validation_data(
        KeyIdentifier=key_arn,
        PrimaryAccountNumber=pan,
        GenerationAttributes={
            "DynamicCardVerificationValue": {
                "CardExpiryDate": expiry,
                "PanSequenceNumber": "00",
                "ApplicationTransactionCounter": "0001",
                "ServiceCode": "101",
            }
        },
    )
    dcvv2 = dcvv2_resp["ValidationData"]
    print(f"   dCVV2 (ATC=0001): {dcvv2}")

    # CAVV
    cavv_resp = data_client.generate_card_validation_data(
        KeyIdentifier=key_arn,
        PrimaryAccountNumber=pan,
        GenerationAttributes={
            "CardHolderVerificationValue": {
                "ApplicationTransactionCounter": "0001",
                "PanSequenceNumber": "00",
                "UnpredictableNumber": "1234",
            }
        },
    )
    cavv = cavv_resp["ValidationData"]
    print(f"   CAVV: {cavv}")

    # PIN (用收单方密钥加密，用于 PIN Translate 场景)
    acquirer_pek_arn = get_key_arn("poc-acquirer-pek")
    pvk_arn = get_key_arn("poc-issuer-pvk")
    acquirer_pin_resp = data_client.generate_pin_data(
        GenerationKeyIdentifier=pvk_arn,
        EncryptionKeyIdentifier=acquirer_pek_arn,
        PrimaryAccountNumber=pan,
        PinBlockFormat="ISO_FORMAT_0",
        GenerationAttributes={"VisaPin": {"PinVerificationKeyIndex": 1}},
        PinDataLength=4,
    )
    acquirer_pin_block = acquirer_pin_resp["EncryptedPinBlock"]
    acquirer_pvv = acquirer_pin_resp["PinData"]["VerificationValue"]
    print(f"   Acquirer PIN Block: {acquirer_pin_block}")
    print(f"   Acquirer PVV: {acquirer_pvv}")

    # MAC (用于 PIN Translate 场景的消息认证)
    mac_key_arn = get_key_arn("poc-mac-key")
    msg_data = "0200542523000044150000000050001234567890"
    mac_resp = data_client.generate_mac(
        KeyIdentifier=mac_key_arn,
        MessageData=msg_data,
        GenerationAttributes={"Algorithm": "ISO9797_ALGORITHM1"},
    )
    mac_value = mac_resp["Mac"]
    print(f"   MAC: {mac_value}")

    # 保存测试数据
    test_card = {
        "pan": pan,
        "expiry_date": expiry,
        "cvv2": cvv2,
        "encrypted_pin_block": pin_data["encrypted_pin_block"],
        "pin_verification_value": pin_data["pin_verification_value"],
        "dcvv2": dcvv2,
        "cavv": cavv,
        "acquirer_pin_block": acquirer_pin_block,
        "acquirer_pvv": acquirer_pvv,
        "mac_message_data": msg_data,
        "mac": mac_value,
    }

    output_path = ".state/test_card.json"
    with open(output_path, "w") as f:
        json.dump(test_card, f, indent=2)
    print(f"\n📁 Test card data saved to {output_path}")
    return test_card


if __name__ == "__main__":
    generate_test_card_data()
