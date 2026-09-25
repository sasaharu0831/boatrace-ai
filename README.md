# ボートレースAI

競艇データを時系列で収集・検証・加工し、予測と買い目を評価するための土台です。

## 対象期間

初期設定は直近3年相当の **2023-09-25〜2026-09-24（日本時間）** です。

## 方針

- GitHubにはコード、データ仕様、小容量サンプルだけをコミットします。
- 大容量の生データ・Parquet・予測ログはGit LFSまたは外部ストレージで管理します。
- データ取得元の利用規約、ライセンス、再配布条件を確認してから設定します。
- 予測時点より後に確定した結果・払戻・確定オッズは特徴量に混ぜません。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config/data_sources.example.yaml config/data_sources.yaml
```

`config/data_sources.yaml` に、利用許諾を確認したデータ提供元のURLと日別ファイルパスを設定します。認証情報は書かず、環境変数で渡してください。

## 実行順

```bash
python scripts/download_three_years.py --dry-run
python scripts/download_three_years.py
python scripts/preprocess_dataset.py --entries data/interim/entries.parquet --results data/interim/results.parquet --before-info data/interim/before_info.parquet
python scripts/validate_dataset.py data/processed/race_lane_dataset.parquet
python scripts/evaluate_predictions.py data/predictions/bets.csv
```

詳細は [`data/README.md`](data/README.md) を参照してください。
