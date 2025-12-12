# Smart Cleanup and Disk Space Optimizer Walkthrough

新しく実装された `cleanup` 機能の動作確認結果をまとめます。

## 実装内容
- **`cortex/packages.py`**: キャッシュ削除と孤立パッケージ検出・削除機能を追加。
- **`cortex/optimizer.py`**: ディスクオプティマイザークラス。スキャンとクリーンアップロジックを実装。
- **`cortex/cli.py`**: `cleanup` コマンドを追加 (`scan` と `run`)。

## 検証結果

### 1. 自動テスト
`pytest tests/test_optimizer.py` により、以下の機能が正常に動作することを確認しました。
- パッケージキャッシュのクリーニング
- 孤立パッケージの検出と削除
- 一時ファイルの削除

### 2. 手動確認: `cleanup scan`
CLIコマンド `cortex cleanup scan` を実行し、システムのスキャンが正常に行われることを確認しました。

**実行結果:**
```text
 CX  │ Scanning for cleanup opportunities...


━━━ Cleanup Opportunities ━━━

📦 Package Cache: 0.00 B
🗑️  Orphaned Packages: 1 packages (~50.00 MB)
📝 Old Logs: 0 files (0.00 B)
🧹 Temp Files: 0 files (0.00 B)

✨ Total Reclaimable: 50.00 MB

Run 'cortex cleanup run --safe' to perform cleanup
```

### 3. 注意点
- **`run` コマンドの実行**: `cortex cleanup run --safe` を実行すると実際にファイルが削除されます。テスト環境での実行では `sudo` 権限が要求される場合があります（パッケージ操作等）。
- **`--safe` フラグ**: 現在の実装では、安全な操作のみが定義されていますが、誤操作防止のため `--safe` フラグまたはユーザー確認を推奨しています。
