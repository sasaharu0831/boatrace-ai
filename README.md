# BOAT LAB Free Research (prototype)

**完全無料の公式B/K取得・証跡・研究データ保管の土台。予想モデルの的中率や実運用は未検証です。**

- Official references: https://www.boatrace.jp/owpc/pc/extra/data/download.html
- Official archives: `https://www1.mbrace.or.jp/od2/{B|K}/YYYYMM/{b|k}YYMMDD.lzh` (全国24場を日単位でまとめたLZH)。
- B=番組表、K=競走成績。LZHの**ダウンロードのみ**実装。展開・選手単位の特徴量抽出は未実装。
- SHA256、URL、取得時刻、保存先をJSONLで記録。BもKも後から収集したものは`HISTORICAL_ONLY`。事前取得証拠がないレースをFORWARDとして評価しない。
- `evaluate` はFORWARD_VERIFIEDかつ事故なしで、事前選択済みの買い目を結果と照合するだけ。払戻は事後評価用であり、選手能力や買い目選択には入力しない。
- `validate_freeze` は時刻・艇番・重複・証跡形式の**構造検証**。第三者による証跡真正性の認証機能は未実装であり、これだけで自動的にFORWARD_VERIFIEDにはしない。

## 無料の実行方法

```bash
python -m unittest discover -s tests -v
python src/boat_free_lab.py collect --start 2026-10-28 --days 1 --root data
pip install duckdb
python src/duckdb_catalog.py --manifest data/manifest.jsonl --db data/archive.duckdb
```

GitHub Actionsは毎日JST 05:35に**2日前のB/Kそれぞれ1件**のみ取得。1ジョブ最大5分、同時起動を抑制。無料の標準ランナーを使う公開リポジトリ向け。`workflow_dispatch`で1日指定も可。

**重要:** GitHub Actions artifactは3日で消える短期保管で、過去4年の永続DBではありません。Actions実行環境も永続ディスクではありません。永続データは別途ローカル保存／プライベート保管先が必要です。現行のリポジトリは公開なのでartifactの公開可能性にも注意してください。実行する前にデータ提供元の利用条件とGitHubの利用規約を確認してください。

このPRでは機密情報もオッズも取得しません。追加課金のあるAPIも使いません。定期処理の開始はこのPRをマージした後です。予想AI、4年一括収集、展示STの対応認証、公式情報の再取得、気象補完、実回収率の算出は今後の別作業です。