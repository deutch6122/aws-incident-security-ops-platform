# scripts

運用・デプロイ・サンプルデータ投入スクリプトを配置する。

## サンプルデータ投入スクリプト（Task 18.1）

dev/MVP 用の **非機微・ダミー** サンプルデータを投入するスクリプト。言語は
Python（`boto3` は遅延 import。import 時に AWS I/O・認証を要求しない）。

| スクリプト | 対象 | 対応要件 |
| --- | --- | --- |
| `seed_alarm_events.py` | ダミーのアラーム風イベントを EventBridge（→SQS）へ投入 | Req 6.1 |
| `seed_finding_events.py` | ダミーの Finding 風イベントを EventBridge（→SQS）へ投入 | Req 6.1 |
| `seed_portal_reports.py` | 非機微レポート・public_status_items を Product_B（DynamoDB/S3）へシード | Req 14.1, 14.2 |
| `seed/common.py` | 共通ヘルパ（CLI・dry-run・非機微チェック・遅延 boto3） | — |

### 使い方

すべてのスクリプトは **既定で dry-run（print-only）**。実 AWS への投入は
`--execute`（別名 `--no-dry-run`）を明示したときのみ行う。

```bash
# dry-run（既定）: ペイロードを表示するだけ。AWS には一切触れない
python3 scripts/seed_alarm_events.py
python3 scripts/seed_finding_events.py --count 5
python3 scripts/seed_portal_reports.py --count 6

# 実投入（明示フラグが必要）
python3 scripts/seed_alarm_events.py --execute
python3 scripts/seed_finding_events.py --execute --region ap-northeast-1
python3 scripts/seed_portal_reports.py --execute \
  --report-metadata-table ops-platform-dev-report-metadata \
  --public-status-table  ops-platform-dev-public-status-items \
  --reports-bucket       ops-platform-dev-portal-REPLACE_WITH_SUFFIX
```

共通引数:

- `--execute` / `--no-dry-run` … 実 AWS へ投入する（未指定時は dry-run）。
- `--dry-run` … 明示的に dry-run（既定なので通常は不要）。
- `--count N` … 生成するダミーレコード件数（既定 3、`N>=1`）。
- `--region` … `--execute` 時のみ使用（既定 `ap-northeast-1`）。

### 安全設計（dry-run 既定・print-only）

- **既定は dry-run**。`--execute` を付けない限り AWS API は一切呼ばれず、
  `boto3` も import されない（`get_boto3_client` は `--execute` 経路でのみ実行）。
- **誤投入防止**。実投入は `--execute` の明示が必須。dry-run では生成ペイロードを
  標準出力に表示するのみ。
- **非機微・ダミーのみ**。生成データに実 ARN・実アカウントID（12桁数値）・実
  Token・実 Secret・実ドメインを含めない。`seed/common.assert_non_sensitive` が
  生成時に検査し、疑わしい値があれば `ValueError` で失敗させる（プレースホルダ
  のみ許容: 例 `ops-platform-dev-resource-0001`、`REPLACE_WITH_SUFFIX`）。
- **A→B 一方向**。`seed_portal_reports.py` は Product_B（DynamoDB/S3）へのみ
  書き込む。Product_A（Aurora/ECS/EKS）へは読み書きしない。

### テスト

`scripts/tests/test_seed_scripts.py` は Terraform/AWS を実行しない静的・単体
テスト。以下を検証する（fake / monkeypatch を使用、実 AWS 非接続）:

- import 時に `boto3` が import されないこと（遅延 import）。
- 既定が dry-run で、`--execute` 未指定時に put/send が呼ばれないこと。
- 生成ペイロードが非機微（ARN・12桁アカウントID・token・secret を含まない）。
- `seed_portal_reports.py` が Product_B のみを対象とし Product_A へ書かないこと。

```bash
python3 -m pytest scripts/tests -q
python3 -m compileall -q scripts
```

## デプロイスクリプト（予定 / Task 19.1）

- `deploy-ecs.sh` … build → ECR push → ECS service update（Req 22.2）
- `deploy-eks.sh` … build → ECR push → `kubectl apply`（Req 22.3）
- `deploy-frontend.sh` … build → S3 sync → CloudFront invalidation（Req 22.4）

> App_Deploy はインフラ apply と分離する。実装は Task 19.1 で追加する。
