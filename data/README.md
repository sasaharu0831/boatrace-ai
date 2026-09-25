# データ管理

## 対象期間

- 2023-09-25 から 2026-09-24 まで（日本時間）

## ディレクトリ

- `data/raw/`: 取得元そのままのファイル。Gitにはコミットしません。
- `data/interim/`: 正規化後、結合前のテーブル。Gitにはコミットしません。
- `data/processed/`: 学習・評価用のParquet。Gitにはコミットしません。
- `data/predictions/`: 予測・買い目・損益ログ。個人情報や購入情報を含む場合はGitに置きません。
- `data/sample/`: スキーマ確認用の匿名化・小容量サンプルのみを置きます。

## 必須テーブル

| テーブル | 主な用途 | 最低限必要な列 |
|---|---|---|
| entries | レース前特徴量 | `race_id`, `race_date`, `venue_code`, `race_number`, `lane`, `racer_id` |
| before_info | 展示・気象など直前特徴量 | `race_id`, `lane` |
| results | 教師ラベル | `race_id`, `lane`, `finish_position` |
| payouts | 回収率計算 | `race_id`, `bet_type`, `combination`, `payout` |

`race_id` は、同一レースを全テーブルで一意に識別できる12桁程度の文字列を推奨します。

## 注意

- 取得元の利用規約、ライセンス、再配布条件を確認してから取得・保存してください。
- 購入時点より後に公開された確定結果や確定オッズを、予測特徴量として混ぜないでください。
- APIキー、Cookie、ログイン情報は設定ファイルに書かず、環境変数で管理してください。
