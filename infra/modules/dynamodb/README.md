# module: dynamodb

Portal_DB。4テーブル（public_status_items / report_metadata[GSI gsi_period] / page_view_logs[TTL] / maintenance_windows[TTL]）、全て PAY_PER_REQUEST を定義する。

- 対応要件: Req 10.1, 11.1, 24.5
- 実装は Task 13.1 で追加する（プレースホルダ）。
