#!/usr/bin/env python3
"""Run offline smoke tests for the bundled TDayPay integration helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def run_json(command: list[str], *, env: dict[str, str] | None = None) -> dict:
    completed = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    return json.loads(completed.stdout)


def main() -> int:
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="tdaypay-integration-test-") as temp:
        project = Path(temp)
        (project / "package.json").write_text(json.dumps({
            "dependencies": {"@nestjs/core": "1", "axios": "1", "class-validator": "1"},
            "devDependencies": {"jest": "1"},
        }), encoding="utf-8")
        (project / "payment-provider.ts").write_text("export const provider = 'test';\n", encoding="utf-8")
        inspection = run_json([sys.executable, str(SCRIPTS / "inspect_project.py"), "--root", str(project)])
        assert inspection["primaryLanguage"] == "TypeScript"
        assert inspection["dependencySignals"]["frameworks"] == ["NestJS"]
        assert inspection["dependencySignals"]["http"] == ["Axios"]
        checks.append("project inspection")

        plan = run_json([
            sys.executable, str(SCRIPTS / "rule_comment_plan.py"), "payout",
            "--currency", "COP", "--payment-type", "NET_BANKING", "--language", "typescript",
        ])
        ids = {rule["id"] for rule in plan["requiredRules"]}
        assert plan["valid"] is True
        assert "COMMON.PAYOUT.REQUIRED_FIELDS" in ids
        assert "COP.PAYOUT.AMOUNT_INTEGER" in ids
        assert "COP.PAYOUT.NET_BANKING.REQUIRED_FIELDS" in ids
        assert {rule["id"] for rule in plan["manualConfirmationRules"]} == {"COP.PAYOUT.AMOUNT_RANGE_CONFLICT"}
        assert any(rule["level"] == "INFO" for rule in plan["informationalRules"])
        assert all(comment.startswith("// TDAYPAY-RULE[") for comment in plan["renderedComments"])
        checks.append("rule comment plan")

        payment_plan = run_json([
            sys.executable, str(SCRIPTS / "rule_comment_plan.py"), "payment",
            "--currency", "MXN", "--payment-type", "SPEI", "--language", "python",
        ])
        payment_ids = {rule["id"] for rule in payment_plan["requiredRules"]}
        assert "COMMON.PAYMENT.REQUIRED_FIELDS" in payment_ids
        assert "COMMON.PAYMENT.MCHORDERID.LENGTH" in payment_ids
        assert "MXN.PAYMENT.SPEI.DYNAMIC.FIXED" in payment_ids
        assert all(comment.startswith("# TDAYPAY-RULE[") for comment in payment_plan["renderedComments"])
        checks.append("payment rule comment plan")

        cop_payment_plan = run_json([
            sys.executable, str(SCRIPTS / "rule_comment_plan.py"), "payment",
            "--currency", "COP", "--payment-type", "PSE", "--language", "typescript",
        ])
        cop_payment_ids = {rule["id"] for rule in cop_payment_plan["requiredRules"]}
        assert cop_payment_plan["paymentType"] == "NET_BANKING"
        assert "COP.PAYMENT.PSE.ALIAS" in cop_payment_ids
        assert "COP.PAYMENT.PAYMENTMETHOD.IF_PRESENT" in cop_payment_ids
        assert "COP.PAYMENT.BENEFICIARYTYPE.ENUM" in cop_payment_ids
        assert "COP.PAYMENT.BENEFICIARYID.CONDITIONAL" in cop_payment_ids
        assert "COP.PAYMENT.IPADDRESS.FORMAT" in cop_payment_ids
        assert "COP.PAYMENT.PRODUCTURL.FORMAT" in cop_payment_ids
        assert "COP.PAYMENT.NET_BANKING.BANKCODE.ENUM" in cop_payment_ids
        assert "COP.PAYMENT.PHONE" in cop_payment_ids
        cop_required_fields = next(rule["behavior"] for rule in cop_payment_plan["requiredRules"] if rule["id"] == "COP.PAYMENT.REQUIRED_FIELDS")
        assert "paymentMethod" not in cop_required_fields
        assert "firstName" not in cop_required_fields
        assert "lastName" not in cop_required_fields
        checks.append("COP payment rule comment plan")

        country = run_json([sys.executable, str(SCRIPTS / "country_rules.py"), "selftest"])
        assert country["valid"] is True
        checks.append(f"country rules {country['passed']}/{country['cases']}")

        callback = run_json([sys.executable, str(SCRIPTS / "tdaypay_callback.py"), "selftest"])
        assert callback == {"valid": True, "cases": 8, "passed": 8}
        callback_comments = run_json([
            sys.executable, str(SCRIPTS / "tdaypay_callback.py"), "comments",
            "--language", "typescript",
        ])
        assert callback_comments["requiredCommentCount"] == 8
        assert "CALLBACK.SIGNATURE.RAW_BODY" in {rule["id"] for rule in callback_comments["requiredRules"]}
        checks.append("callback verification 8/8")

        body = project / "payout.json"
        body.write_text(json.dumps({
            "mchOrderId": "COPTEST0001", "amount": "5000", "currency": "COP",
            "purpose": "test", "beneficiaryName": "Test Recipient",
            "beneficiaryEmail": "test@example.com", "beneficiaryMobile": "3001234567",
            "beneficiaryAccountNumber": "123456789",
        }), encoding="utf-8")
        test_env = os.environ.copy()
        test_env.update({"TDAYPAY_MCH_ID": "test-merchant", "TDAYPAY_MERCHANT_KEY": "test-key"})
        prepared = run_json([
            sys.executable, str(SCRIPTS / "tdaypay_request.py"), "payout",
            "--body-file", str(body), "--timestamp", "1700000000",
        ], env=test_env)
        assert prepared["mode"] == "prepare-only"
        assert prepared["headers"]["method"] == "payOut"
        checks.append("prepare-only transaction")

    print(json.dumps({"valid": True, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
