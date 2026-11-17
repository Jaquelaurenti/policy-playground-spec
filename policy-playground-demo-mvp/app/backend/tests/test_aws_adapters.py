"""Fluxo completo com os adaptadores AWS (DynamoDB + S3) contra o moto, sem conta real."""
import os
import unittest

try:
    import boto3
    from moto import mock_aws
except ImportError:  # moto é dependência só de teste
    mock_aws = None


@unittest.skipIf(mock_aws is None, "moto não instalado")
class AwsAdaptersFlow(unittest.TestCase):
    def setUp(self):
        os.environ.update(AWS_DEFAULT_REGION="us-east-1", AWS_ACCESS_KEY_ID="test", AWS_SECRET_ACCESS_KEY="test",
                          PP_STORE="dynamodb", PP_TABLE="pp-test", PP_AUDIT_BUCKET="pp-audit-test", PP_SYNC_JOBS="1")
        self.mock = mock_aws()
        self.mock.start()
        boto3.client("dynamodb").create_table(
            TableName="pp-test", BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}])
        boto3.client("s3").create_bucket(Bucket="pp-audit-test")

    def tearDown(self):
        self.mock.stop()
        for k in ("PP_STORE", "PP_TABLE", "PP_AUDIT_BUCKET", "PP_SYNC_JOBS"):
            os.environ.pop(k, None)

    def test_full_flow_persists_and_audits(self):
        from fastapi.testclient import TestClient
        from policy_playground.api.app import build_playground, create_app
        c = TestClient(create_app(build_playground()))
        h = {"X-Demo-User": "esp", "X-Demo-Roles": "Policy Specialist"}
        hid = c.post("/api/hypotheses", json={"intent": "renda mínima para 3000"}, headers=h).json()["hypothesis"]["hypothesisId"]
        self.assertEqual(c.post(f"/api/hypotheses/{hid}/scenarios", json={"overrides": {"P001": 3000}}, headers=h).status_code, 200)
        ex = c.post(f"/api/hypotheses/{hid}/executions", json={}, headers=h).json()
        r = c.get(f"/api/executions/{ex['executionId']}", headers=h).json()
        self.assertEqual(r["jobState"], "done")
        self.assertEqual(r["comparison"]["outputs"]["resultado"]["changedRecords"], ["S02", "S03", "S04"])
        again = c.post(f"/api/hypotheses/{hid}/executions", json={}, headers=h).json()
        self.assertTrue(c.get(f"/api/executions/{again['executionId']}", headers=h).json()["reused"])
        c.post(f"/api/hypotheses/{hid}/suggestions", json={}, headers=h)
        rec = c.get(f"/api/hypotheses/{hid}", headers=h).json()
        self.assertGreaterEqual(len(rec["findings"]), 2)
        self.assertEqual(len(c.get("/api/hypotheses", headers=h).json()), 1)
        keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket="pp-audit-test")["Contents"]]
        self.assertEqual(len(keys), rec["events"])


if __name__ == "__main__":
    unittest.main()
