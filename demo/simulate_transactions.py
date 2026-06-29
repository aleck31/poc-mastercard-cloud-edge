"""
演示脚本 - 模拟交易场景
可本地直接运行（调用 Lambda handler）或通过 API Gateway 调用
"""
import json
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "issuer_host"))
from handler import authorize_transaction  # noqa: E402

# 加载测试卡数据
TEST_CARD_PATH = os.path.join(os.path.dirname(__file__), "..", ".state", "test_card.json")
if os.path.exists(TEST_CARD_PATH):
    with open(TEST_CARD_PATH) as f:
        TEST_CARD = json.load(f)
else:
    TEST_CARD = {
        "pan": "5425230000004415", "expiry_date": "0127",
        "cvv2": "000", "encrypted_pin_block": "", "pin_verification_value": "",
        "dcvv2": "000", "cavv": "000",
    }
    print("⚠️  .state/test_card.json not found, using placeholder values")


def print_result(scenario, result):
    code = result["response_code"]
    icon = "✅" if code == "00" else "❌"
    print(f"\n{'─' * 60}")
    print(f"{icon} Scenario: {scenario}")
    print(f"{'─' * 60}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def scenario_emv_chip_transaction():
    """场景1: 芯片卡 POS 刷卡 - EMV ARQC 验证"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "emv",
        "pan": "5425230000004415",
        "pan_sequence": "00",
        "amount": 1500,
        "currency": "HKD",
        "merchant": "7-Eleven Hong Kong",
        "arqc": "A1B2C3D4E5F60718",
        "transaction_data": "00010000000015000800000000000000007640000000000034425052000000000000000000000000",
    }


def scenario_ecommerce_transaction():
    """场景2: 电商无卡交易 - CVV2 验证（正确）"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "ecommerce",
        "pan": TEST_CARD["pan"],
        "amount": 299,
        "currency": "HKD",
        "merchant": "HKTVmall",
        "expiry_date": TEST_CARD["expiry_date"],
        "cvv2": TEST_CARD["cvv2"],
    }


def scenario_ecommerce_wrong_cvv():
    """场景2b: 电商无卡交易 - CVV2 错误（欺诈检测）"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "ecommerce",
        "pan": "5425230000004415",
        "amount": 1200,
        "currency": "HKD",
        "merchant": "Suspicious Online Store",
        "expiry_date": "0127",
        "cvv2": "999",
    }


def scenario_contactless_dcvv2():
    """场景3: 非接触式支付 - dCVV2 动态验证"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "contactless",
        "pan": TEST_CARD["pan"],
        "amount": 88,
        "currency": "HKD",
        "merchant": "Octopus Top-up MTR",
        "expiry_date": TEST_CARD["expiry_date"],
        "pan_sequence": "00",
        "atc": "0001",
        "service_code": "101",
        "dcvv2": TEST_CARD["dcvv2"],
    }


def scenario_contactless_replay_attack():
    """场景3b: 非接触式支付 - dCVV2 重放攻击拦截"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "contactless",
        "pan": TEST_CARD["pan"],
        "amount": 88,
        "currency": "HKD",
        "merchant": "Replayed Transaction",
        "expiry_date": TEST_CARD["expiry_date"],
        "pan_sequence": "00",
        "atc": "0009",  # 错误的 ATC，模拟重放攻击
        "service_code": "101",
        "dcvv2": TEST_CARD["dcvv2"],
    }


def scenario_atm_withdrawal():
    """场景: ATM 取款 - PIN 验证"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "atm",
        "pan": TEST_CARD["pan"],
        "amount": 5000,
        "currency": "HKD",
        "merchant": "HSBC ATM Causeway Bay",
        "encrypted_pin_block": TEST_CARD["encrypted_pin_block"],
        "pin_verification_value": TEST_CARD["pin_verification_value"],
    }


def scenario_pin_translate():
    """场景: PIN 翻译完整链路（MAC验证 → PIN翻译 → PIN验证）"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "pin_translate",
        "pan": TEST_CARD["pan"],
        "amount": 2000,
        "currency": "HKD",
        "merchant": "POS Terminal - Park N Shop",
        "encrypted_pin_block": TEST_CARD["acquirer_pin_block"],
        "pin_verification_value": TEST_CARD["acquirer_pvv"],
        "outgoing_format": "ISO_FORMAT_0",
        "message_data": TEST_CARD["mac_message_data"],
        "mac": TEST_CARD["mac"],
    }


def scenario_mac_tampered():
    """场景: MAC 验证失败 - 消息被篡改"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "mac_verify",
        "pan": TEST_CARD["pan"],
        "amount": 9999,
        "currency": "HKD",
        "merchant": "Tampered Message",
        "message_data": "0200542523000044150000000099991234567890",  # 金额被篡改
        "mac": TEST_CARD["mac"],  # 原始 MAC（与篡改后的消息不匹配）
    }


def scenario_encrypt_pan():
    """场景: PAN 加密（敏感数据保护）"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "encrypt",
        "pan": "5425230000004415",
        "amount": 0,
        "currency": "HKD",
        "merchant": "Data Protection",
    }


def scenario_key_export():
    """场景: TR-31 密钥导出（与外部系统交换密钥）"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "key_export",
        "pan": "",
        "amount": 0,
        "currency": "",
        "merchant": "Key Exchange",
        "key_alias": "poc-mac-key",
    }


def scenario_3ds_cavv():
    """场景: 3D Secure CAVV 验证"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "3ds",
        "pan": TEST_CARD["pan"],
        "amount": 1500,
        "currency": "HKD",
        "merchant": "Online Store (3DS)",
        "pan_sequence": "00",
        "atc": "0001",
        "unpredictable_number": "1234",
        "cavv": TEST_CARD["cavv"],
    }


def scenario_card_personalization():
    """场景: 卡片个人化密钥派生"""
    return {
        "transaction_id": str(uuid.uuid4()),
        "transaction_type": "card_personalization",
        "pan": TEST_CARD["pan"],
        "amount": 0,
        "currency": "",
        "merchant": "Card Personalization Bureau",
        "expiry_date": TEST_CARD["expiry_date"],
        "pan_sequence": "00",
    }


def main():
    print()
    print("=" * 60)
    print("🏦 Mastercard Cloud Edge POC - Issuer Authorization Demo")
    print("   Simulating Hong Kong Issuer on AWS Payment Cryptography")
    print("=" * 60)

    scenarios = [
        ("EMV Chip Card - POS Purchase (7-Eleven HK)", scenario_emv_chip_transaction),
        ("E-commerce - Online Purchase (HKTVmall)", scenario_ecommerce_transaction),
        ("E-commerce - Wrong CVV (Fraud Attempt)", scenario_ecommerce_wrong_cvv),
        ("Contactless - dCVV2 (Octopus Top-up)", scenario_contactless_dcvv2),
        ("Contactless - dCVV2 Replay Attack", scenario_contactless_replay_attack),
        ("ATM Cash Withdrawal (HSBC ATM)", scenario_atm_withdrawal),
        ("PIN Translate Pipeline (MAC→Translate→Verify)", scenario_pin_translate),
        ("MAC Verification - Tampered Message", scenario_mac_tampered),
        ("PAN Encryption (Data Protection)", scenario_encrypt_pan),
        ("TR-31 Key Export (Key Exchange)", scenario_key_export),
        ("3D Secure - CAVV Verification", scenario_3ds_cavv),
        ("Card Personalization - Key Derivation", scenario_card_personalization),
    ]

    for name, scenario_fn in scenarios:
        request = scenario_fn()
        print(f"\n📤 Request: {name}")
        print(f"   PAN: {request['pan'][:6]}****{request['pan'][-4:]}")
        print(f"   Amount: {request['currency']} {request['amount']}")

        try:
            result = authorize_transaction(request)
            print_result(name, result)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("   (Ensure keys are set up: python src/key_management/setup_keys.py)")

    print(f"\n{'=' * 60}")
    print("Demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
