# Runbook（障害対応・運用手順）

design.md の「Error Handling / 障害時の考慮 / コスト最適化（撤去）」を要約する（Req 26.1, 26.3）。実装済みの内容（監視 module / seed・deploy スクリプト / A→B 連携）を反映する。

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

## アラーム発生時（CloudWatch Alarm → SNS）

`infra/modules/monitoring` の Alarm が SNS 通知を発報したときの一次対応。

1. SNS 通知から発報 Alarm を特定（対象: SQS DLQ>0 / ECS CPU・Mem・タスク数 / ALB 5xx・レイテンシ / Lambda Errors・Throttles・Duration / Aurora ACU・接続数）。
2. Product_A / Product_B のどちらのダッシュボードかを確認（監視は A/B 分離 2 ダッシュボード）。
3. 該当リソースの CloudWatch Logs を確認（ECS/EKS/Lambda/ALB/VPC Flow、保持 14〜30 日）。相関 ID（500 応答時）で API ログを突合。
4. 一時的な負荷なら復旧を待ち、恒常的なら下記の個別対応（DLQ / Finding 等）へ。

## Finding 発生時（Worker_Finding 取込）

1. `security-finding-worker` が SQS の Finding 風イベントを取り込み、`findings` / `finding_triage` へ整合登録する（同一 `external_id` は冪等・重複しない）。
2. Backend_API の `GET /findings` / `GET /findings/{id}` で登録内容・重大度・対応ステータスを確認。
3. 対応ステータス変更は API 経由で行い、`audit_logs` に変更前後値が 1 件記録されることを確認（Property 6）。
4. 判定結果が想定値域外・未取込の場合は当該メッセージの DLQ 有無を確認（下記）。

## DLQ > 0 時

- DLQ メッセージ数 > 0 で CloudWatch Alarm を発報 → SNS 通知。
- CloudWatch Logs でワーカー（`alarm-event-processor` / `security-finding-worker`）の失敗要因を確認。
- 原因修正後に再投入。再処理は `external_id UNIQUE` の冪等取込のため重複レコードを作らない。
- 恒常的に処理不能なメッセージは内容を記録のうえ破棄を手動判断（dev/MVP）。

## Portal 閲覧確認

1. Viewer が Cognito でログイン → CloudFront 経由で Status Portal を閲覧。
2. `GET /api/status`（一覧）/ `GET /api/status/{id}`（詳細）/ `GET /api/reports`（一覧）/ `GET /api/reports/{id}`（詳細）が JWT 付きで応答することを確認。
3. 閲覧ごとに `page_view_logs` がちょうど 1 件増加し、`public_status_items` 本体は変更されないこと（Property 10、閲覧は副作用最小）。
4. 未登録レポート ID は 404、JWT 欠落/無効は 401 を返すことを確認。

## A→B 連携確認

1. A→B 連携の実行主体は **`monthly-summary-cronjob`（Cronjob_Summary）に限定**。Backend_API から Portal への直接書き込み経路は無い。
2. CronJob 実行後、Portal_Storage(`reports/<period>/summary.json`) 配置・`report_metadata` 登録・`public_status_items` 反映を確認。
3. キーは決定的で再実行しても重複せず上書き（`period` / `external_id` UNIQUE の冪等）。
4. **B→A（Product_B → Product_A）への書き込み・参照が発生していないこと**を確認（設計上排除。連携は非機微・ダミーのみ）。

## ロールバック観点（App_Deploy）

App_Deploy（`scripts/deploy-*.sh`）は既定 dry-run。実行は `--execute` 明示時のみ。ロールバック時も同様に dry-run で内容を確認してから実行する。

- **ECS**: 直前の安定イメージタグで `deploy-ecs.sh --tag <前タグ> --execute`（service を force new deployment で切替）。ECS のデプロイ履歴/前タスク定義へ戻す。
- **EKS**: 直前タグで `deploy-eks.sh --tag <前タグ> --execute` を再適用、または `kubectl rollout undo` で Deployment を戻す。
- **Frontend**: 直前の静的成果物で `deploy-frontend.sh --execute`（S3 sync）→ CloudFront invalidation（`/*`）でキャッシュを更新。
- インフラ（terraform）のロールバックは App_Deploy とは分離。Infra_Pipeline の plan→承認→apply 経路で扱い、App_Deploy スクリプトからは terraform を呼ばない。

## 削除・停止前の確認

破壊的操作の前に必ず確認する。

- 進行中の CronJob / 未処理 SQS / DLQ に未対応メッセージが無いか。
- コスト影響大リソース（Aurora / NAT / EKS / CloudFront）を止める前に、他タスクへの影響が無いか。
- S3（Portal_Storage / artifact）・ECR イメージの中身を残す必要が無いか（`terraform destroy` 前に空にする必要がある）。
- Aurora は削除前に final snapshot / スナップショット取得の要否を判断。
- Secrets Manager / CloudWatch Logs / WAF Web ACL の取り残しが無いか。

## 撤去（削除）手順

コスト影響が大きい **Aurora / NAT Gateway / EKS / CloudFront** を含むため、依存の逆順で撤去する。破壊的操作のためユーザー承認後にのみ実行する。

1. App レイヤ停止（ECS desired_count=0 / service 削除、EKS Deployment・CronJob 削除、CloudFront 無効化）。
2. S3 / ECR の中身削除（`terraform destroy` 前に空にする）。
3. 本体インフラ撤去（`terraform -chdir=infra/environments/dev plan -destroy` で確認 → 承認後 `destroy`）。
4. Bootstrap を最後に手動削除（state S3 / artifact S3 を空にしてから、DynamoDB lock table があれば併せて削除）。
5. 残存確認（CloudWatch Logs / Secrets Manager / WAF Web ACL の取り残しがないか）。

> App の停止は `scripts/deploy-*.sh` ではなく、ECS service の desired_count=0 / EKS の `kubectl delete -f apps/eks-workers/k8s/` / CloudFront 無効化で行う。`terraform destroy` は本タスクでは実行せず、実施時は README「削除（撤去）手順」に従う。
