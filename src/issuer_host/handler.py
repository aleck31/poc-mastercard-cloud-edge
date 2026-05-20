"""
发卡方核心业务逻辑 - Issuer Host
处理来自 Mastercard 网络的授权请求
"""
import boto3
import json
import os
from datetime import datetime, timezone

REGION = os.environ.get("AWS_REGION", "ap-southeast-1")
data_client = boto3.client("payment-cryptography-data", region_name=REGION)
control_client = boto3.client("payment-cryptography", region_name=REGION)


def get_key_arn(alias):
    """通过别名获取密钥 ARN"""
    resp = control_client.get_alias(AliasName=f"alias/{alias}")
    return resp["Alias"]["KeyArn"]


def verify_cvv2(pan, expiry_date, cvv2):
    """验证 CVV2（电商无卡交易）"""
    key_arn = get_key_arn("poc-issuer-cvk")
    try:
        data_client.verify_card_validation_data(
            KeyIdentifier=key_arn,
            PrimaryAccountNumber=pan,
            VerificationAttributes={
                "CardVerificationValue2": {"CardExpiryDate": expiry_date}
            },
            ValidationData=cvv2,
        )
        return {"verified": True, "method": "CVV2"}
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "CVV2", "reason": "CVV2 mismatch"}


def verify_dcvv2(pan, expiry_date, pan_sequence, atc, service_code, dcvv2):
    """验证 dCVV2（动态卡验证值，防重放攻击）"""
    key_arn = get_key_arn("poc-issuer-dcvv2-imk")
    try:
        data_client.verify_card_validation_data(
            KeyIdentifier=key_arn,
            PrimaryAccountNumber=pan,
            VerificationAttributes={
                "DynamicCardVerificationValue": {
                    "CardExpiryDate": expiry_date,
                    "PanSequenceNumber": pan_sequence,
                    "ApplicationTransactionCounter": atc,
                    "ServiceCode": service_code,
                }
            },
            ValidationData=dcvv2,
        )
        return {"verified": True, "method": "dCVV2"}
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "dCVV2", "reason": "dCVV2 verification failed (possible replay attack)"}


def verify_arqc(pan, pan_sequence, arqc, transaction_data):
    """验证 ARQC 并生成 ARPC（芯片卡交易）"""
    key_arn = get_key_arn("poc-issuer-imk-ac")
    try:
        resp = data_client.verify_auth_request_cryptogram(
            KeyIdentifier=key_arn,
            TransactionData=transaction_data,
            AuthRequestCryptogram=arqc,
            MajorKeyDerivationMode="EMV_OPTION_A",
            SessionKeyDerivationAttributes={
                "EmvCommon": {
                    "PrimaryAccountNumber": pan,
                    "PanSequenceNumber": pan_sequence,
                    "ApplicationTransactionCounter": transaction_data[:4],
                }
            },
            AuthResponseAttributes={"ArpcMethod1": {"AuthResponseCode": "3030"}},
        )
        return {
            "verified": True,
            "method": "ARQC",
            "arpc": resp.get("AuthResponseValue", ""),
        }
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "ARQC", "reason": "ARQC verification failed"}


def verify_pin(pan, encrypted_pin_block, pin_verification_value):
    """验证 PIN（ATM 取款）"""
    pek_arn = get_key_arn("poc-issuer-pek")
    pvk_arn = get_key_arn("poc-issuer-pvk")
    try:
        data_client.verify_pin_data(
            VerificationKeyIdentifier=pvk_arn,
            EncryptionKeyIdentifier=pek_arn,
            PrimaryAccountNumber=pan,
            PinBlockFormat="ISO_FORMAT_0",
            EncryptedPinBlock=encrypted_pin_block,
            VerificationAttributes={
                "VisaPin": {
                    "PinVerificationKeyIndex": 1,
                    "VerificationValue": pin_verification_value,
                }
            },
        )
        return {"verified": True, "method": "PIN"}
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "PIN", "reason": "PIN incorrect"}


def translate_pin(pan, encrypted_pin_block, incoming_format="ISO_FORMAT_0", outgoing_format="ISO_FORMAT_0"):
    """PIN 翻译：收单方密钥 → 发卡方密钥（可选格式转换）"""
    acquirer_pek_arn = get_key_arn("poc-acquirer-pek")
    issuer_pek_arn = get_key_arn("poc-issuer-pek")
    try:
        resp = data_client.translate_pin_data(
            IncomingKeyIdentifier=acquirer_pek_arn,
            OutgoingKeyIdentifier=issuer_pek_arn,
            IncomingTranslationAttributes={"IsoFormat0": {"PrimaryAccountNumber": pan}},
            OutgoingTranslationAttributes={
                outgoing_format.replace("ISO_FORMAT_", "IsoFormat"): {"PrimaryAccountNumber": pan}
            },
            EncryptedPinBlock=encrypted_pin_block,
        )
        return {
            "success": True,
            "method": "PIN_TRANSLATE",
            "translated_pin_block": resp["PinBlock"],
            "outgoing_format": outgoing_format,
        }
    except Exception as e:
        return {"success": False, "method": "PIN_TRANSLATE", "reason": str(e)}


def generate_mac(message_data):
    """生成交易消息 MAC"""
    mac_key_arn = get_key_arn("poc-mac-key")
    resp = data_client.generate_mac(
        KeyIdentifier=mac_key_arn,
        MessageData=message_data,
        GenerationAttributes={"Algorithm": "ISO9797_ALGORITHM1"},
    )
    return {"mac": resp["Mac"], "method": "MAC_GENERATE"}


def verify_mac(message_data, mac):
    """验证交易消息 MAC"""
    mac_key_arn = get_key_arn("poc-mac-key")
    try:
        data_client.verify_mac(
            KeyIdentifier=mac_key_arn,
            MessageData=message_data,
            Mac=mac,
            VerificationAttributes={"Algorithm": "ISO9797_ALGORITHM1"},
        )
        return {"verified": True, "method": "MAC"}
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "MAC", "reason": "MAC verification failed - message tampered"}


def encrypt_pan(pan):
    """加密 PAN（敏感数据保护）"""
    key_arn = get_key_arn("poc-data-encrypt-key")
    pan_hex = pan.encode().hex()
    resp = data_client.encrypt_data(
        KeyIdentifier=key_arn,
        PlainText=pan_hex,
        EncryptionAttributes={"Symmetric": {"Mode": "CBC"}},
    )
    return {"cipher_text": resp["CipherText"], "method": "ENCRYPT"}


def decrypt_pan(cipher_text):
    """解密 PAN"""
    key_arn = get_key_arn("poc-data-encrypt-key")
    resp = data_client.decrypt_data(
        KeyIdentifier=key_arn,
        CipherText=cipher_text,
        DecryptionAttributes={"Symmetric": {"Mode": "CBC"}},
    )
    return {"plain_text": bytes.fromhex(resp["PlainText"]).decode(), "method": "DECRYPT"}


def export_key_tr31(key_alias):
    """TR-31 密钥导出"""
    key_arn = get_key_arn(key_alias)
    kek_arn = get_key_arn("poc-kek")
    resp = control_client.export_key(
        ExportKeyIdentifier=key_arn,
        KeyMaterial={"Tr31KeyBlock": {"WrappingKeyIdentifier": kek_arn}},
    )
    return {
        "method": "TR31_EXPORT",
        "key_block": resp["WrappedKey"]["KeyMaterial"],
        "kcv": resp["WrappedKey"]["KeyCheckValue"],
    }


def verify_cavv(pan, pan_sequence, atc, unpredictable_number, cavv):
    """验证 CAVV（3D Secure 持卡人认证）"""
    key_arn = get_key_arn("poc-issuer-dcvv2-imk")
    try:
        data_client.verify_card_validation_data(
            KeyIdentifier=key_arn,
            PrimaryAccountNumber=pan,
            VerificationAttributes={
                "CardHolderVerificationValue": {
                    "ApplicationTransactionCounter": atc,
                    "PanSequenceNumber": pan_sequence,
                    "UnpredictableNumber": unpredictable_number,
                }
            },
            ValidationData=cavv,
        )
        return {"verified": True, "method": "CAVV_3DS"}
    except data_client.exceptions.VerificationFailedException:
        return {"verified": False, "method": "CAVV_3DS", "reason": "CAVV verification failed - 3DS authentication invalid"}


def derive_card_key(pan, expiry_date, pan_sequence):
    """卡片个人化：从 IMK 为特定卡片派生唯一密钥并生成验证值"""
    key_arn = get_key_arn("poc-issuer-dcvv2-imk")
    resp = data_client.generate_card_validation_data(
        KeyIdentifier=key_arn,
        PrimaryAccountNumber=pan,
        GenerationAttributes={
            "DynamicCardVerificationValue": {
                "CardExpiryDate": expiry_date,
                "PanSequenceNumber": pan_sequence,
                "ApplicationTransactionCounter": "0001",
                "ServiceCode": "101",
            }
        },
    )
    return {
        "method": "CARD_KEY_DERIVATION",
        "pan_masked": pan[:6] + "****" + pan[-4:],
        "derived_validation": resp["ValidationData"],
        "key_check_value": resp["KeyCheckValue"],
    }


def authorize_transaction(event):
    """
    交易授权主入口
    接收 ISO 20022 风格的授权请求，返回授权响应
    """
    tx_type = event.get("transaction_type")
    pan = event.get("pan")
    amount = event.get("amount", 0)

    # 密码学验证
    if tx_type == "emv":
        crypto_result = verify_arqc(
            pan=pan,
            pan_sequence=event.get("pan_sequence", "00"),
            arqc=event["arqc"],
            transaction_data=event["transaction_data"],
        )
    elif tx_type == "ecommerce":
        crypto_result = verify_cvv2(
            pan=pan,
            expiry_date=event["expiry_date"],
            cvv2=event["cvv2"],
        )
    elif tx_type == "contactless":
        crypto_result = verify_dcvv2(
            pan=pan,
            expiry_date=event["expiry_date"],
            pan_sequence=event.get("pan_sequence", "00"),
            atc=event["atc"],
            service_code=event.get("service_code", "101"),
            dcvv2=event["dcvv2"],
        )
    elif tx_type == "atm":
        crypto_result = verify_pin(
            pan=pan,
            encrypted_pin_block=event["encrypted_pin_block"],
            pin_verification_value=event["pin_verification_value"],
        )
    elif tx_type == "pin_translate":
        # 完整链路：MAC 验证 → PIN 翻译 → PIN 验证
        results = {}
        # Step 1: 验证消息 MAC
        if event.get("mac"):
            mac_result = verify_mac(event.get("message_data", ""), event["mac"])
            results["mac_verification"] = mac_result
            if not mac_result["verified"]:
                return build_response("96", "MAC verification failed", event, mac_result)
        # Step 2: PIN 翻译（收单方 → 发卡方）
        translate_result = translate_pin(
            pan=pan,
            encrypted_pin_block=event["encrypted_pin_block"],
            outgoing_format=event.get("outgoing_format", "ISO_FORMAT_0"),
        )
        results["pin_translate"] = translate_result
        if not translate_result["success"]:
            return build_response("96", "PIN translation failed", event, translate_result)
        # Step 3: 用翻译后的 PIN Block 验证
        crypto_result = verify_pin(
            pan=pan,
            encrypted_pin_block=translate_result["translated_pin_block"],
            pin_verification_value=event["pin_verification_value"],
        )
        crypto_result["pipeline"] = results
    elif tx_type == "mac_verify":
        crypto_result = verify_mac(event.get("message_data", ""), event.get("mac", ""))
    elif tx_type == "encrypt":
        crypto_result = encrypt_pan(pan)
    elif tx_type == "decrypt":
        crypto_result = decrypt_pan(event.get("cipher_text", ""))
    elif tx_type == "key_export":
        crypto_result = export_key_tr31(event.get("key_alias", "poc-mac-key"))
    elif tx_type == "3ds":
        crypto_result = verify_cavv(
            pan=pan,
            pan_sequence=event.get("pan_sequence", "00"),
            atc=event["atc"],
            unpredictable_number=event["unpredictable_number"],
            cavv=event["cavv"],
        )
    elif tx_type == "card_personalization":
        crypto_result = derive_card_key(
            pan=pan,
            expiry_date=event["expiry_date"],
            pan_sequence=event.get("pan_sequence", "00"),
        )
    else:
        return build_response("96", "System malfunction", event)

    # 授权决策
    if not crypto_result.get("verified", crypto_result.get("success", True)):
        return build_response("05", "Do not honour", event, crypto_result)

    # 简单额度检查（演示用）
    credit_limit = 50000
    if amount > credit_limit:
        return build_response("51", "Insufficient funds", event, crypto_result)

    return build_response("00", "Approved", event, crypto_result)


def build_response(response_code, message, request, crypto_result=None):
    """构建 ISO 20022 风格的授权响应"""
    return {
        "message_type": "pacs.002",
        "response_code": response_code,
        "response_message": message,
        "transaction_id": request.get("transaction_id", ""),
        "pan_masked": request.get("pan", "")[:6] + "****" + request.get("pan", "")[-4:],
        "amount": request.get("amount"),
        "currency": request.get("currency", "HKD"),
        "crypto_verification": crypto_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "arpc": crypto_result.get("arpc", "") if crypto_result else "",
    }


# Lambda handler
def lambda_handler(event, context):
    """AWS Lambda 入口"""
    body = json.loads(event["body"]) if isinstance(event.get("body"), str) else event
    result = authorize_transaction(body)
    return {
        "statusCode": 200 if result["response_code"] == "00" else 400,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,x-api-key",
        },
        "body": json.dumps(result),
    }
