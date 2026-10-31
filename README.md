# BOAT LAB Free Research — 検証用ドラフト

**追加の有料APIやクレジット購入なし**で BOAT RACE 公式B（番組表）・K（競走成績）を調査するための Python 研究基盤です。

## 確認済み（2026-10-31 JST）

- 公式 B/K 日別 LZH を少量取得し、無料の 7z で展開、CP932 で読み取れることを GitHub Actions で確認。
- 2026-10-27〜29 の3日分：B 420レース、K 413レース、B/K共通413レース、6艇の登録番号・艇番・着順・3連単が整合する**歴史的記録363レース**。
- 2026-10-28の106レースについて一時SQLiteにB 636艇行・K 636艇行を保存し、2回の取り込みでも重複0。
- B由来の特徴量とK由来の結果・払戻を**別CSV**に出力。着順・払戻を予想入力に混ぜないチェック済み。
- 異常な割合値、登録番号重複、距離不一致、出典ハッシュ変更、レース数の減少は隔離・自動置換拒否。
- Pythonテスト70件成功。詳細: [GitHub Actions](https://github.com/sasaharu0831/boatrace-ai/actions/runs/41094310877)。
- 3日分の件数・公式ファイルSHA-256・例外理由は [集計JSON](research/verified_coverage_2026-10-27_to_29.json) に記録（**生アーカイブは保存されていない**）。

## 追加の別期間SHADOW検証（2026-10-20〜22）

`src/holdout_analysis.py` は、以前の10/27〜29の履歴実験で使った3つの固定モデル（艇番のみ・当地勝率・当地勝率＋モーター）を**係数変更なし**で、前回と重複しない10/20〜22の公式B/Kを用いて再検証します。Bのみから3連単8点を先に凍結し、K結果で歴史的に仮想採点。正確な締切前Forward採点ではありません。

| 8点／1点100円と仮定 | 前回363R 的中率／回収率 | 別期間406R 的中率／回収率 | 6日合算769R 的中率／回収率 |
| --- | --- | --- | --- |
| 艇番のみ | 30.6% / 69.0% | 31.0% / 67.9% | 30.8% / 68.4% |
| 艇番＋当地勝率 | 31.4% / 58.5% | 37.2% / 83.1% | 34.5% / 71.4% |
| 艇番＋当地勝率＋モーター | 30.6% / 57.7% | 36.9% / 84.9% | 33.9% / 72.1% |

- 報告書: [別期間406R・会場別・レース種別・K側特殊記載別・6日合算](research/independent_holdout_8pt_20261020_22.json)。
- 公式データ実測ログ: https://github.com/sasaharu0831/boatrace-ai/actions/runs/41149550566
- Python自動テスト83件成功: https://github.com/sasaharu0831/boatrace-ai/actions/runs/41149550546
- 新しい分母は**歴史的6艇整合レース406R**で、事故なし完全証明・真の未来予測ではありません。Kの特殊・事故関連の記載があるものを別集計し、記載なしも「安全確認済み」にはしません。
- 3モデルすべて回収率100%未満／的中率50%未満。**本番モデルは変更せず採用保留**。会場別の小標本から勝ちパターンを後付け選定することは禁止。

## 大切な区別

- **363レースはデータの整合件数であり、予想的中数ではありません。**
- `FORWARD_VERIFIED` を予想ファイルに書くだけでは真正Forwardとして採点できません。第三者検証できる締切前の確定証跡が未実装のため、Forwardの的中率・回収率は算出不可。明示的 `--research-only` の仮想検証は別分母です。
- B/Kともに過去レース終了後に得たデータとして `HISTORICAL_ONLY`。締切前Capture・Freezeの真正な証拠がないため、**真正Forward評価は0レース**。
- 6艇が正常に結合しても、事故なし・安定板なしの確定証明にはなりません。準優・優勝戦・不明レースは別分母で扱い、未検証は学習に採用しません。
- 公式データ配布元: https://www.boatrace.jp/owpc/pc/extra/data/download.html 。収集前に提供条件・利用規約を確認してください。

## 実行（ローカルに保存先がある場合）

Python 3.12以上と無償の 7z/p7zip-full が必要です。公開リポジトリのGitHub標準ランナーでの検証は確認済みですが、そのディスクは一時的であり、**4年分の継続保存には使えません**。

```bash
# テスト（公式サーバーへのアクセスなし）
python -m unittest discover -s tests -v

# 約4年分の収集計画（ネットワークアクセスなし）
python src/archive_backfill.py plan

# オフライン整合監査：元のSHA・欠損・破損・再試行回数を確認
python src/archive_health.py --root /ABSOLUTE/PERSISTENT/DISK/boatdata

# 既存の永続ローカルディスクへ、1回最大B/K合計6ファイルずつ取得・保存
python src/persistent_history.py \
  --root /ABSOLUTE/PERSISTENT/DISK/boatdata \
  --max-files 6 --max-imports 3

# 別のディスク／保存先に検証付き増分バックアップ（有料APIなし）
python src/offline_backup.py \
  --source /ABSOLUTE/PERSISTENT/DISK/boatdata \
  --backup /ABSOLUTE/SECOND-STORAGE/boatdata-backup \
  --max-files 24

# 元の端末がなくても、バックアップ先のみでファイルの整合性を検証
python src/offline_backup.py \
  --backup /ABSOLUTE/SECOND-STORAGE/boatdata-backup \
  --verify-only
```

詳細: [4年分の手順と制限](docs/four-year-backfill.md)。

## 現在、動かしていないもの

- **GitHubの日次自動収集は無効**。公式サーバーへアクセスする検証ワークフローも手動専用。
- **本番の予測モデルや買い目は未接続**。本当に締切前に取得したデータで作る予想が必要。
- **4年分の永続データ収集は未完了**。利用可能な保存先が自動接続されていない。
- **ドラフトPR内の開発コード**。mainにはマージしておらず、自動運転は開始していません。
- 追加API課金は使っていませんが、保存機器・通信・電力・容量まで無料保証するものではありません。
- バックアップはSDカード等のハードリンク非対応媒体でも排他作成＋SHA-256照合で対応。電源断による不完全なファイルは `--verify-only` で再確認してください。

### 構成

`src/boat_free_lab.py` 少量取得・履歴監査、
`src/archive_backfill.py` 4年分インベントリー、
`src/lzh_extract.py` 厳格なLZH展開、
`src/historical_records.py` B/K照合、
`src/historical_sqlite.py` 履歴DB、
`src/quality_policy.py` レース分類・未確認保留、
`src/historical_export.py` 事前/事後CSV分離、
`src/persistent_history.py` ローカル保存と再開、
`src/offline_backup.py` 増分コピー・SQLiteスナップショット・ハッシュ検証。
