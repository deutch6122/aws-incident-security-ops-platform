# module: messaging (SQS + EventBridge、alarm / finding の 2 系統)

非同期経路の入口を、**alarm 系統**と**finding 系統**の 2 系統に分離して定義する。
各系統が独立の EventBridge rule・SQS Standard Queue・専用 DLQ・target・queue policy・
DLQ redrive-allow policy を所有し、相互のキューを参照しない（Req 6.1, 6.2）。リトライ
超過のメッセージは自系統 DLQ に移動する（Req 6.4）。

リソースは `local.systems`（`alarm` / `finding`）に対する `for_each` で生成し、同じ定義を
系統ごとに重複記述しない。

## 構成（各系統ごとに 1 つずつ）

| リソース | 役割 |
| --- | --- |
| `aws_sqs_queue.main[系統]` | 系統のメイン Standard Queue。ワーカーが受信/削除する。 |
| `aws_sqs_queue.dlq[系統]` | 系統専用 DLQ。`maxReceiveCount` 超過を退避する。 |
| `aws_sqs_queue.main[系統].redrive_policy` | `deadLetterTargetArn`＝自系統 DLQ、`maxReceiveCount`＝`sqs_max_receive_count`。 |
| `aws_sqs_queue_redrive_allow_policy.dlq[系統]` | DLQ を使えるのは自系統メインキューのみ（最小権限）。 |
| `aws_cloudwatch_event_rule.this[系統]` | 系統の EventBridge rule。 |
| `aws_cloudwatch_event_target.this[系統]` | rule → 自系統メインキューへの配送ターゲット。 |
| `aws_sqs_queue_policy.this[系統]` | `events.amazonaws.com` からの `SendMessage` を自系統 rule ARN 限定で許可。 |

alarm 系統は 2 個、finding 系統は 2 個の queue（main + DLQ）を持ち、rule / queue / DLQ は
それぞれ合計 2 個ずつになる。

## detail-type によるルーティング

- alarm rule: `source = [event_source]`（既定 `ops-platform.sample`）＋
  `detail-type = alarm_event_detail_types`（既定 `["AlarmEvent"]`）に一致したイベントを
  **alarm queue のみ**へ配送する。
- finding rule: 同じ source ＋ `detail-type = finding_event_detail_types`
  （既定 `["SecurityFinding"]`）に一致したイベントを **finding queue のみ**へ配送する。
- 両 rule は相手系統の queue を target にしない。

event source は seed script と同じ `ops-platform.sample`。detail-type は空集合・空文字を
variable validation で拒否する。

## DLQ redrive（maxReceiveCount 超過で移動）

各系統のメインキューの `redrive_policy` に自系統 DLQ の ARN と `maxReceiveCount`
（`sqs_max_receive_count`、既定 5）を設定する。`maxReceiveCount` 回を超えて受信された
メッセージは SQS により自系統 DLQ へ移される。DLQ 側は `redrive_allow_policy` により
自系統メインキューからのみ利用を許可する（系統間で分離）。

## Queue policy の SourceArn 限定

各キューポリシーは Principal を `Service = events.amazonaws.com` に限定し、さらに
`Condition aws:SourceArn = <自系統 rule ARN>` を付与する。これにより自系統 rule
以外（相手系統 rule を含む）からの `SendMessage` を拒否する（最小権限）。

## Standard queue / 暗号化（SSE-SQS）

すべてのキューは FIFO ではなく Standard Queue（`fifo_queue` 設定なし）。メインキュー・
DLQ とも `sqs_managed_sse_enabled = true`（SSE-SQS）で保存時暗号化する。カスタマーキー
素材やシークレットはコードに一切含まない。

## 入力変数

- `name_prefix`（必須）/ `common_tags`（必須）
- `alarm_event_detail_types`（既定 `["AlarmEvent"]`、空拒否）
- `finding_event_detail_types`（既定 `["SecurityFinding"]`、空拒否）
- `sqs_max_receive_count`（既定 5）
- `event_source`（既定 `ops-platform.sample`）
- `visibility_timeout_seconds` / `message_retention_seconds` / `dlq_message_retention_seconds`
  / `receive_wait_time_seconds` / `sqs_managed_sse`

## 出力

系統別に queue / DLQ の name・url・arn と rule ARN を出力する。

- alarm: `alarm_queue_name` / `alarm_queue_url` / `alarm_queue_arn` /
  `alarm_dlq_name` / `alarm_dlq_url` / `alarm_dlq_arn` / `alarm_event_rule_arn`
- finding: `finding_queue_name` / `finding_queue_url` / `finding_queue_arn` /
  `finding_dlq_name` / `finding_dlq_url` / `finding_dlq_arn` / `finding_event_rule_arn`

## dev root 配線

dev rootへ配線済みです。queue ARN/URLはEKS workerのIRSAとmanifest renderへ、DLQ名はmonitoringへ渡します。実配送とmax-receive挙動はCategory Cです。

## テスト

`tests/test_messaging_snapshot.py` は Terraform/AWS を実行しない静的テスト。rule/queue/DLQ
が 2 系統分存在すること、alarm と finding の detail-type が異なること、各 target が自系統
queue のみ参照すること、各 queue policy が自系統 rule のみ許可すること、各 DLQ が自系統
queue のみ許可すること、`sqs_max_receive_count` 既定 5、FIFO 設定が存在しないこと、
系統別 output・機微リテラル非混入を検証する。

## 検証分類

- Category A（本 Task で必須）: 上記静的テスト、`terraform validate`。
- Category B（保留）: mock / LocalStack による EventBridge → SQS ルーティング検証。
- Category C（保留）: 実 EventBridge 配送、実 max-receive 挙動（Req 6.3, 6.4, 6.7）。
