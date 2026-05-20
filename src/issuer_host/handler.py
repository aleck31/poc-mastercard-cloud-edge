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
    elif tx_type == "atm":
        crypto_result = verify_pin(
            pan=pan,
            encrypted_pin_block=event["encrypted_pin_block"],
            pin_verification_value=event["pin_verification_value"],
        )
    else:
        return build_response("96", "System malfunction", event)

    # 授权决策
    if not crypto_result["verified"]:
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
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result),
    }
