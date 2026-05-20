"""
CDK Stack - Issuer Host on AWS
模拟发卡方通过 Mastercard Cloud Edge 接入支付网络
"""
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct


class IssuerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Lambda - Issuer Host
        issuer_fn = _lambda.Function(
            self, "IssuerHost",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="handler.lambda_handler",
            code=_lambda.Code.from_asset("../src/issuer_host"),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={"AWS_REGION_OVERRIDE": "ap-southeast-1"},
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        # 授予 Payment Cryptography 权限
        # Control Plane: 获取密钥别名和元数据
        issuer_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "payment-cryptography:GetAlias",
                "payment-cryptography:GetKey",
                "payment-cryptography:ListAliases",
            ],
            resources=[
                f"arn:aws:payment-cryptography:ap-southeast-1:{self.account}:alias/*",
                f"arn:aws:payment-cryptography:ap-southeast-1:{self.account}:key/*",
            ],
        ))
        # Data Plane: 密码学验证操作（Data Plane 不支持资源级限制，必须用 *）
        issuer_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "payment-cryptography-data:VerifyCardValidationData",
                "payment-cryptography-data:VerifyPinData",
                "payment-cryptography-data:VerifyAuthRequestCryptogram",
                "payment-cryptography-data:GenerateMac",
            ],
            resources=["*"],
        ))

        # API Gateway - 模拟 Cloud Edge 入口
        api = apigw.RestApi(
            self, "CloudEdgeAPI",
            rest_api_name="Mastercard Cloud Edge (Simulated)",
            description="Simulated Mastercard Cloud Edge endpoint for Issuer authorization",
            deploy_options=apigw.StageOptions(stage_name="v1"),
        )

        # POST /authorize - 授权请求（需要 API Key）
        authorize = api.root.add_resource("authorize")
        authorize.add_method("POST", apigw.LambdaIntegration(issuer_fn), api_key_required=True)

        # API Key + Usage Plan
        api_key = api.add_api_key("PocApiKey", api_key_name="poc-cloud-edge-key")
        plan = api.add_usage_plan("PocUsagePlan",
            name="poc-plan",
            throttle=apigw.ThrottleSettings(rate_limit=10, burst_limit=5),
            quota=apigw.QuotaSettings(limit=1000, period=apigw.Period.DAY),
        )
        plan.add_api_stage(stage=api.deployment_stage)
        plan.add_api_key(api_key)

        # 输出 API URL
        from aws_cdk import CfnOutput
        CfnOutput(self, "ApiUrl", value=api.url, description="Cloud Edge API endpoint")
        CfnOutput(self, "ApiKeyId", value=api_key.key_id, description="API Key ID (use 'aws apigateway get-api-key --api-key <id> --include-value' to retrieve)")
