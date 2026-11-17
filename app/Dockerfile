# Imagem única do backend: a mesma roda local (docker run -p 8080:8080) e na Lambda.
# Na Lambda, o Lambda Web Adapter traduz eventos HTTP do API Gateway em chamadas ao uvicorn;
# eventos não-HTTP (os jobs assíncronos {"ppJob": ...}) chegam como POST /events.
# Build a partir da raiz do repositório: docker build -f app/Dockerfile .
FROM public.ecr.aws/docker/library/python:3.12-slim
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
WORKDIR /srv
COPY app/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/backend/policy_playground ./policy_playground
# Policy Spec sintético: copiado como está, nunca alterado (R16.3).
COPY .kiro/specs/policy-playground/fixtures ./fixtures
ENV PP_FIXTURES=/srv/fixtures \
    PORT=8080 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/api/health \
    AWS_LWA_PASS_THROUGH_PATH=/events \
    PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn policy_playground.api.app:app --host 0.0.0.0 --port ${PORT}"]
