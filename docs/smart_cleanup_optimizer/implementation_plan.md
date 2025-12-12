# Smart Cleanup and Disk Space Optimizer Implementation Plan

不要なファイルや最適化されていないリソースを特定し、クリーンアップする機能を実装します。

## ユーザーレビューが必要な事項
- `apt-get autoremove` などのシステムコマンドを自動実行するため、管理者権限が必要になる場合があります。`sudo` の取り扱いに注意が必要です。
- ログ圧縮機能は `cortex` 自身のログを対象としますが、システムログ (`/var/log`) は対象外とします（安全のため）。

## 提案される変更

### cortex

#### [MODIFY] [packages.py](file://wsl.localhost/Ubuntu/home/momopon1415/cortex/cortex/packages.py)
- `PackageManager` クラスに以下のメソッドを追加します:
    - `clean_cache()`: パッケージマネージャーのキャッシュを削除 (`apt-get clean` 等)。
    - `get_orphaned_packages()`: 不要になった依存パッケージを取得 (`apt-get autoremove --dry-run` のパース等、または `deborphan` コマンドが使えるか確認。シンプルに `autoremove` コマンドを利用予定)。
    - `remove_packages(packages)`: パッケージリストを削除。

#### [NEW] [optimizer.py](file://wsl.localhost/Ubuntu/home/momopon1415/cortex/cortex/optimizer.py)
- `DiskOptimizer` クラスを実装します。
    - **スキャン機能**:
        - パッケージキャッシュサイズ
        - 孤立パッケージ（数とサイズ）
        - 古いログファイル（サイズ）
        - 一時ファイル（サイズ）
    - **クリーンアップ実行**:
        - キャッシュクリーニング
        - 孤立パッケージ削除
        - ログ圧縮（`.gz` 化）
        - 一時ファイル削除

#### [MODIFY] [cli.py](file://wsl.localhost/Ubuntu/home/momopon1415/cortex/cortex/cli.py)
- `cleanup` サブコマンドを追加します。
    - `scan`: 現在の状態をスキャンして表示。
    - `run [--safe]`: クリーンアップを実行。`--safe` フラグがある場合、各ステップで確認を求めるか、または安全な項目のみ実行する（仕様では「Safe cleanup mode」とあるので、安全な項目のみ実行、あるいはユーザー確認を行うモードとする）。

### tests

#### [NEW] [test_optimizer.py](file://wsl.localhost/Ubuntu/home/momopon1415/cortex/tests/test_optimizer.py)
- `DiskOptimizer` のユニットテスト。
- モックを使用してシステムコマンド実行をシミュレート。

## 検証計画

### 自動テスト
- `make test` を実行し、新しいテストと既存のテストがパスすることを確認します。
- `pytest tests/test_optimizer.py` を重点的に実行します。

### 手動検証
1. `cortex cleanup scan` を実行し、現状のディスク使用状況が表示されることを確認。
2. `cortex cleanup run --safe` を実行し、シミュレーションまたは安全な削除が実行されることを確認。
3. 実際に不要なファイルを作成し、それらが検出・削除されるか確認（テスト環境にて）。
