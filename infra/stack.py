"""Stack do perfil demo. Mapeamento para a arquitetura-alvo em arquitetura/arquitetura-da-aplicacao.md §10.3 (ADR-19).

Alvo (produção)                         →  Demo (custo zero)
ECS Fargate + ALB + VPC endpoints       →  Lambda (mesma imagem, via Lambda Web Adapter)
SQS + worker                            →  Lambda se auto-invocando em modo Event (jobs idempotentes)
API Gateway REST + WAF                  →  API Gateway HTTP API + autorizador JWT do Cognito + throttling
DynamoDB / S3 Object Lock + KMS CMK     →  DynamoDB on-demand / S3 só-escrita com SSE-S3
Bedrock (Claude)                        →  Bedrock Amazon Nova (opcional) ou sem modelo
"""
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_authorizers as authorizers,
    aws_apigatewayv2_integrations as integrations,
    aws_budgets as budgets,
    aws_cloudfront as cf,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_dynamodb as ddb,
    aws_ecr_assets as ecr_assets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
)
from constructs import Construct

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    "policy-specialist": "Policy Specialist: cria hipóteses, executa cenários e decide",
    "risk-approver": "Risk Approver: registra decisões",
    "data-analyst": "Data Analyst: consulta",
    "viewer": "Viewer: somente leitura",
}


class PolicyPlaygroundDemo(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, *, alert_email: str, model_id: str, budget_usd: float, **kw) -> None:
        super().__init__(scope, cid, description="Policy Playground: perfil demo de custo zero (dados sintéticos)", **kw)
        destroy = cdk.RemovalPolicy.DESTROY
        fn_name = f"{cid}-api"

        # --- Dados: tabela única (eventos append-only + índice + chaves de idempotência) e trilha de auditoria
        table = ddb.Table(self, "Store", partition_key=ddb.Attribute(name="pk", type=ddb.AttributeType.STRING),
                          sort_key=ddb.Attribute(name="sk", type=ddb.AttributeType.STRING),
                          billing_mode=ddb.BillingMode.PAY_PER_REQUEST, removal_policy=destroy)
        audit = s3.Bucket(self, "Audit", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
                          encryption=s3.BucketEncryption.S3_MANAGED, versioned=True,
                          lifecycle_rules=[s3.LifecycleRule(noncurrent_version_expiration=cdk.Duration.days(30))],
                          removal_policy=destroy, auto_delete_objects=True)

        # --- Identidade: Cognito com grupos = papéis do produto; sem auto-cadastro
        pool = cognito.UserPool(self, "Users", self_sign_up_enabled=False, sign_in_aliases=cognito.SignInAliases(email=True),
                                password_policy=cognito.PasswordPolicy(min_length=12),
                                account_recovery=cognito.AccountRecovery.EMAIL_ONLY, removal_policy=destroy,
                                user_invitation=cognito.UserInvitationConfig(
                                    email_subject="Policy Playground: seu acesso à demo",
                                    email_body="Usuário {username}, senha temporária {####}. Você vai definir a sua no primeiro login."))
        for name, desc in GROUPS.items():
            cognito.CfnUserPoolGroup(self, f"G-{name}", user_pool_id=pool.user_pool_id, group_name=name, description=desc)
        domain = pool.add_domain("Domain", cognito_domain=cognito.CognitoDomainOptions(
            domain_prefix=f"pp-demo-{cdk.Aws.ACCOUNT_ID}"))

        # --- Backend: a mesma imagem do container, na Lambda
        fn = lambda_.DockerImageFunction(
            self, "Api", function_name=fn_name,
            code=lambda_.DockerImageCode.from_image_asset(str(ROOT), file="app/Dockerfile",
                                                          platform=ecr_assets.Platform.LINUX_AMD64),
            architecture=lambda_.Architecture.X86_64, memory_size=1024, timeout=cdk.Duration.seconds(120),   # job do agente (R17); o HTTP API segue cortando em 30 s
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={"PP_STORE": "dynamodb", "PP_TABLE": table.table_name, "PP_AUDIT_BUCKET": audit.bucket_name,
                         "PP_AUTH": "cognito", "PP_MODEL_ID": model_id, "PP_SUGGESTION_CAP": "5",
                         "PP_MAX_SUGGESTION_REQUESTS": "3", "PP_MCP": "on"})
        table.grant_read_write_data(fn)
        fn.add_to_role_policy(iam.PolicyStatement(actions=["s3:PutObject"], resources=[audit.arn_for_objects("events/*")]))
        # Auto-invocação para os jobs assíncronos. ARN montado pelo nome para não criar dependência circular.
        fn.add_to_role_policy(iam.PolicyStatement(actions=["lambda:InvokeFunction"], resources=[
            f"arn:{cdk.Aws.PARTITION}:lambda:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:function:{fn_name}"]))
        if model_id:
            fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[
                f"arn:{cdk.Aws.PARTITION}:bedrock:*::foundation-model/*",
                f"arn:{cdk.Aws.PARTITION}:bedrock:*:{cdk.Aws.ACCOUNT_ID}:inference-profile/*"]))
        # Jobs não são reprocessados automaticamente: o próprio usuário reenvia (idempotente).
        fn.configure_async_invoke(retry_attempts=0, max_event_age=cdk.Duration.minutes(5))

        # --- Front-end: S3 privado + CloudFront; /api/* vai para o HTTP API (mesma origem, sem CORS)
        site = s3.Bucket(self, "Site", block_public_access=s3.BlockPublicAccess.BLOCK_ALL, enforce_ssl=True,
                         encryption=s3.BucketEncryption.S3_MANAGED, removal_policy=destroy, auto_delete_objects=True)
        api = apigw.HttpApi(self, "Http", api_name=f"{cid}-http", create_default_stage=True)
        dist = cf.Distribution(
            self, "Cdn", default_root_object="index.html", price_class=cf.PriceClass.PRICE_CLASS_100,
            comment="Policy Playground demo",
            default_behavior=cf.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(site),
                                                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                response_headers_policy=cf.ResponseHeadersPolicy.SECURITY_HEADERS),
            additional_behaviors={"/api/*": cf.BehaviorOptions(
                origin=origins.HttpOrigin(cdk.Fn.select(2, cdk.Fn.split("/", api.api_endpoint))),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                cache_policy=cf.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER)})
        site_url = f"https://{dist.distribution_domain_name}/"

        client = pool.add_client(
            "Web", generate_secret=False, prevent_user_existence_errors=True,
            auth_flows=cognito.AuthFlow(user_srp=True),
            id_token_validity=cdk.Duration.hours(1), access_token_validity=cdk.Duration.hours(1),
            o_auth=cognito.OAuthSettings(flows=cognito.OAuthFlows(authorization_code_grant=True),
                                         scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.EMAIL, cognito.OAuthScope.PROFILE],
                                         callback_urls=[site_url], logout_urls=[site_url]))

        # Só /api/* é exposto; POST /events (jobs) fica inacessível de fora.
        api.add_routes(path="/api/{proxy+}", methods=[apigw.HttpMethod.ANY],
                       integration=integrations.HttpLambdaIntegration("Lambda", fn),
                       authorizer=authorizers.HttpJwtAuthorizer(
                           "Jwt", f"https://cognito-idp.{cdk.Aws.REGION}.amazonaws.com/{pool.user_pool_id}",
                           jwt_audience=[client.user_pool_client_id]))
        # Servidor MCP do Playground (R17.6): mesmo autorizador JWT; o ator vem do token, como na API.
        api.add_routes(path="/mcp/{proxy+}", methods=[apigw.HttpMethod.ANY],
                       integration=integrations.HttpLambdaIntegration("LambdaMcp", fn),
                       authorizer=authorizers.HttpJwtAuthorizer(
                           "JwtMcp", f"https://cognito-idp.{cdk.Aws.REGION}.amazonaws.com/{pool.user_pool_id}",
                           jwt_audience=[client.user_pool_client_id]))
        stage = api.default_stage.node.default_child
        stage.default_route_settings = apigw.CfnStage.RouteSettingsProperty(throttling_burst_limit=20, throttling_rate_limit=10)

        s3deploy.BucketDeployment(self, "Publish", destination_bucket=site, distribution=dist, distribution_paths=["/*"],
                                  memory_limit=512, sources=[
                                      s3deploy.Source.asset(str(ROOT / "app" / "frontend" / "dist")),
                                      s3deploy.Source.json_data("config.json", {
                                          "auth": "cognito", "clientId": client.user_pool_client_id, "redirectUri": site_url,
                                          "cognitoDomain": f"{domain.domain_name}.auth.{cdk.Aws.REGION}.amazoncognito.com"})])

        # --- FinOps: alerta em US$ 1 (20%) e no teto, real e previsto
        if alert_email:
            subs = [budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)]
            notes = [budgets.CfnBudget.NotificationWithSubscribersProperty(
                notification=budgets.CfnBudget.NotificationProperty(notification_type=t, comparison_operator="GREATER_THAN",
                                                                    threshold=pct, threshold_type="PERCENTAGE"),
                subscribers=subs) for t, pct in (("ACTUAL", 20), ("ACTUAL", 100), ("FORECASTED", 100))]
            budgets.CfnBudget(self, "Budget", budget=budgets.CfnBudget.BudgetDataProperty(
                budget_name=f"{cid}-mensal", budget_type="COST", time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(amount=budget_usd, unit="USD")),
                notifications_with_subscribers=notes)

        cdk.CfnOutput(self, "Url", value=site_url, description="Abra aqui a demo")
        cdk.CfnOutput(self, "UserPoolId", value=pool.user_pool_id)
        cdk.CfnOutput(self, "FunctionName", value=fn.function_name)
        cdk.CfnOutput(self, "McpUrl", value=f"{api.api_endpoint}/mcp/stream", description="Servidor MCP (Bearer: token do Cognito)")
