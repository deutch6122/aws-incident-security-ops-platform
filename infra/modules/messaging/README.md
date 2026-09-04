# module: messaging (SQS + EventBridge)

非同期経路の入口を定義する。EventBridge rule がサンプルイベントを受け、SQS
Standard Queue に配送する。ワーカーがキューを消費し、リトライ超過のメッセージ
は DLQ に移動する（Req 6.1, 6.4）。

## 構成

| リソース | 役割 |
| --- | --- |
| `aws_sqs_queue.main` | メインの Standard Queue。ワーカーが受信/削除する。 |
| `aws_sqs_queue.dlq` | DLQ。`maxReceiveCount` 超過のメッセージを退避する。 |
| `aws_sqs_queue.main.redrive_policy` | `deadLetterTargetArn`＝DLQ ARN、`maxReceiveCount`＝再受信上限。 |
| `aws_sqs_queue_redrive_allow_policy.dlq` | DLQ を使えるのはメインキューのみに限定（最小権限）。 |
| `aws_cloudwatch_event_rule.this` | サンプルイベント投入用の EventBridge rule。 |
| `aws_cloudwatch_event_target.this` | rule → メインキューへの配送ターゲット。 |
| `aws_sqs_queue_policy.this` | `events.amazonaws.com` からの `SendMessage` を rule ARN 限定で許可。 |

## DLQ redrive（maxReceiveCount 超過で移動）

メインキューの `redrive_policy` に DLQ の ARN と `maxReceiveCount`（既定 5）を設定
する。ワーカーのハンドラが失敗するとメッセージは削除されず、visibility timeout
後に再配送される。`maxReceiveCount` 回を超えて受信されたメッセージは SQS により
DLQ へ移される。DLQ 側は `redrive_allow_policy` によりメインキューからのみ利用を
許可する。

## EventBridge → SQS 配送

`aws_cloudwatch_event_rule` は `eventbridge_event_pattern`（既定は
`source = ["ops-platform.sample"]`）に一致したイベントを、input transformer を
使わずそのままメインキューへ配送する。ワーカーはイベント本文（body）を JSON と
して解析する。

## Queue policy の SourceArn 限定

キューポリシーは Principal を `Service = events.amazonaws.com` に限定し、さらに
`Condition aws:SourceArn = <rule ARN>` を付与することで、この EventBridge rule
以外からの `SendMessage` を拒否する（最小権限）。

## 暗号化（SSE-SQS）

メインキュー・DLQ とも `sqs_managed_sse_enabled = true`（SSE-SQS）で保存時暗号化
する。カスタマーキー素材やシークレットはコードに一切含まない。

## EKS worker との接続点

- `queue_arn` → eks モジュールの `sqs_queue_arns` に渡す（worker role の
  `ReceiveMessage` / `DeleteMessage` 権限を当該 ARN に限定）。
- `queue_url` → `eks-workers` の Deployment 環境変数 `WORKER_SQS_QUEUE_URL` に
  渡す。
- `dlq_arn` → monitoring モジュール（Task 18.2）で DLQ 深度 > 0 のアラームに
  利用する。

## dev root への配線について（後続依存）

`infra/environments/dev` への本モジュール配線は、eks モジュール等との整合が確定
してから行う。alb/ecs/eks と同じ「実装したものだけ配線」方針に従い、Task 11 時点
では dev ルートへは配線しない。

## テスト

`tests/test_messaging_snapshot.py` は Terraform/AWS を実行しない静的テスト。
redrive 設定・EventBridge rule/target・queue policy（`events.amazonaws.com` ＋
`aws:SourceArn`）・SSE-SQS・outputs・命名/タグ・機微リテラル非混入を検証する。
