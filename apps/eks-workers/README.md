# apps/eks-workers

Product_A の EKS ワーカー群（Python）。namespace=`workers`、EKS Fargate 上で稼働。単一の `workers/` パッケージに共通ロジックと 3 種のエントリポイントをまとめ、1 つのコンテナイメージを `command` で切り替えて起動する。

## ワーカー種別（エントリポイント）

| ワーカー | k8s 種別 | エントリポイント | 役割 |
| --- | --- | --- | --- |
| Worker_Alarm (`alarm-event-processor`) | Deployment | `python -m workers.entrypoints.alarm_event_processor` | SQS からアラーム風イベントを取得→`alarm_events` へ冪等 upsert→メッセージ削除（Req 6.2, 6.5）。 |
| Worker_Finding (`security-finding-worker`) | Deployment | `python -m workers.entrypoints.security_finding_worker` | 重大度/リソース種別/対応ステータスを判定→`findings`/`finding_triage` へ整合登録・冪等（Req 6.3）。 |
| Cronjob_Summary (`monthly-summary-cronjob`) | CronJob | `python -m workers.entrypoints.monthly_summary_cronjob` | 対象年月の集計→`monthly_summaries` へ period UNIQUE upsert（Req 7.1, 7.2）。**A→B 連携は Phase 3 のため未実装**。 |

## パッケージ構成

```
workers/
  config.py                共通設定（非シークレットのみ。DB Secret は ARN 参照）
  sqs.py                   SQS Protocol + boto3 アダプタ + receive/process/delete ループ
  stores.py                リポジトリ Protocol と in-memory fake（テスト用の DB 代替）
  alarm.py                 Worker_Alarm コアロジック（純関数 + 冪等 upsert）
  finding.py               Worker_Finding 判定（純関数）+ 整合登録
  summary.py               Cronjob_Summary 集計（純関数）+ period upsert
  db/
    secrets.py             Secrets Manager から DB 認証情報を安全取得（ARN 参照/遅延/redaction）
    models.py              SQLAlchemy モデル（db/migrations/0001_init_schema.sql と整合）
    session.py             遅延エンジン生成（import 時に AWS/DB へ接続しない）
    repositories.py        SQLAlchemy 実装（ON CONFLICT による DB 冪等）
  entrypoints/             各ワーカーの実行入口
```

## SQS 受信/削除と at-least-once（Req 6.5）

`workers/sqs.py` の `process_batch` は、**ハンドラが成功した後にのみメッセージを削除**する。ハンドラが例外を送出したメッセージは削除せず、可視性タイムアウト後に SQS が再配送する。規定回数を超えた失敗は DLQ へ移動する（DLQ 設定は Task 11 の messaging モジュール）。at-least-once 配送を前提とし、冪等 upsert（`external_id` UNIQUE）で重複を無害化する。

## Secrets Manager / DB 接続の扱い

- DB 認証情報は **Secrets Manager の ARN 参照のみ**（`WORKER_DB_SECRET_ARN`）。パスワードや接続 URL 全体は設定・ログ・例外・manifest に一切現れない。
- `workers/db/secrets.py` は backend-api の `app/db/secrets.py` と同一方針（ARN 参照・boto3 遅延生成・URL は `URL.create` で安全構築・エラーメッセージに値を埋めない）。
- **import 時に AWS/DB へ接続しない**。boto3 クライアントと SQLAlchemy エンジンは初回利用時に生成する。

## Kubernetes manifest（`k8s/`）

| ファイル | 内容 |
| --- | --- |
| `00-namespace.yaml` | namespace `workers`（eks module の Fargate profile / IRSA sub 条件と一致）。 |
| `10-serviceaccounts.yaml` | ServiceAccount `eks-worker` / `eks-cronjob`。IRSA ロール ARN を **プレースホルダ** annotation で紐付け。 |
| `20-alarm-event-processor.yaml` | Worker_Alarm Deployment。 |
| `21-security-finding-worker.yaml` | Worker_Finding Deployment。 |
| `30-monthly-summary-cronjob.yaml` | Cronjob_Summary CronJob（schedule 例）。 |
| `40-fargate-logging.yaml` | `aws-observability` namespace + `aws-logging` ConfigMap（`output=cloudwatch_logs`）。**Fluent Bit DaemonSet は使わない**。 |

### プレースホルダの置換方法

manifest には実 ARN・実イメージ URI を書かない。以下のプレースホルダをデプロイ時に置換する（`envsubst` や kustomize/helm 変数など）:

- `${EKS_WORKER_ROLE_ARN}` … eks module 出力 `worker_role_arn`
- `${EKS_CRONJOB_ROLE_ARN}` … eks module 出力 `cronjob_role_arn`
- `${ECR_WORKERS_IMAGE}` … eks-workers の ECR イメージ URI
- `${WORKER_DB_SECRET_ARN}` … aurora module 出力（Secrets Manager ARN、値ではない）
- `${WORKER_SQS_QUEUE_URL}` … messaging module（Task 11）のキュー URL
- `${AWS_REGION}` / `${WORKER_LOG_GROUP_NAME}` … region と eks module 出力 `worker_log_group_name`

例（`envsubst` 使用時、実 apply はデプロイスクリプトで実施）:

```
export EKS_WORKER_ROLE_ARN=... EKS_CRONJOB_ROLE_ARN=... ECR_WORKERS_IMAGE=... \
       WORKER_DB_SECRET_ARN=... WORKER_SQS_QUEUE_URL=... \
       AWS_REGION=ap-northeast-1 WORKER_LOG_GROUP_NAME=/ops-platform-dev/eks/workers
for f in k8s/*.yaml; do envsubst < "$f" | kubectl apply -f -; done
```

> Secret（DB パスワード等）を base64 化して Kubernetes Secret に置くことはしない。DB 認証情報は IRSA 経由で実行時に Secrets Manager から取得する。

## テスト

実 AWS / 実 DB へ接続しない。`SQLAlchemy` 依存はある環境では実行し、無い環境では `pytest.importorskip` で skip する。純関数（判定・集計・period 計算・parse）は標準ライブラリのみで実行できる。

- 単体テスト: Secret redaction、import 時非接続、SQS delete が処理成功後のみ、判定値域、集計整合。
- Property 7/8/9: Hypothesis（`max_examples>=100`）。DB は in-memory fake（`workers.stores`）で代替（Docker/testcontainers 不使用の制約による。詳細は `workers/stores.py` の注記参照）。

```
python3 -m pytest apps/eks-workers/tests -q -rs
```
