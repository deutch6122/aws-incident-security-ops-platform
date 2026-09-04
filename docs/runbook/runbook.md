# Runbook（障害対応・運用手順）

design.md の「Error Handling / 障害時の考慮 / コスト最適化（撤去）」を要約する（Req 26.1, 26.3）。詳細は Task 19.2 で拡充する（プレースホルダ）。

## 障害時対応

| 障害 | 影響と挙動 | 対応 |
| --- | --- | --- |
| Backend_API 停止 | 同期 API 不可。非同期処理と Product_B は継続 | ECS がタスク再起動。疎結合で波及最小 |
| EKS ワーカー障害 | 取込/集計が遅延。API 参照は継続 | SQS がメッセージ保持、復旧後に再開 |
| SQS 処理失敗 | 一時失敗は再配送、恒常失敗は DLQ | DLQ アラーム→調査→再投入 |
| Aurora 一時不可 | 書込/参照失敗（503） | Serverless v2 復旧待ち。SDK リトライ |
| CronJob 失敗 | 月次集計と A→B 連携が遅延 | `backoffLimit` 再試行、次回スケジュールで回復 |
| CloudFront/Portal 障害 | 閲覧不可。Product_A 運用は継続 | 疎結合で Product_A に波及しない |
| A→B 連携失敗 | Portal のレポート/ステータス更新が遅延 | 次回 CronJob で再反映（冪等） |

## DLQ 運用方針

- DLQ メッセージ数 > 0 で CloudWatch Alarm を発報 → SNS 通知。
- 原因調査後に再投入または破棄を手動判断（dev/MVP）。
- 再処理は `external_id UNIQUE` による冪等取込のため、重複レコードを作らずに安全に行える。

## 撤去（削除）手順

コスト影響が大きい **Aurora / NAT Gateway / EKS / CloudFront** を含むため、依存の逆順で撤去する。破壊的操作のためユーザー承認後にのみ実行する。

1. App レイヤ停止（ECS desired_count=0 / service 削除、EKS Deployment・CronJob 削除、CloudFront 無効化）。
2. S3 / ECR の中身削除（`terraform destroy` 前に空にする）。
3. 本体インフラ撤去（`terraform -chdir=infra/environments/dev plan -destroy` で確認 → 承認後 `destroy`）。
4. Bootstrap を最後に手動削除（state S3 / artifact S3 を空にしてから、DynamoDB lock table があれば併せて削除）。
5. 残存確認（CloudWatch Logs / Secrets Manager / WAF Web ACL の取り残しがないか）。

> 詳細な撤去チェックリストは Task 19.x で拡充する。
