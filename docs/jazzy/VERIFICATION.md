# Pixi / Jazzy 検証記録

実施日: 2026-09-17

文書更新: 2026-09-18（forkの目的・帰属・パッチ適用手順を追記し、READMEの日本語版と
言語切り替えリンクを追加。ライセンス保持と追加部分のライセンス表記を確認し、
CIバッジ、Docker公開ジョブのfork条件、Docker用ActionsのNode.js 24対応を追記。
統合パッチを再生成して適用を確認）

## 対象

- 上流: `aerostack2/aerostack2`、`19c397309c6a41b279e6b551818ec12605cfcecc`
- 適用済み: Jazzy対応パッチと通信タイムアウトr1パッチ。旧パッチ2件は削除し、
  [統合パッチ](../../patch/aerostack2-jazzy-r2.patch) に集約済み
- 追加: ROS起動CLIの依存、`jazzy-check`、Pixi回帰CI、ルートlockの保存
- 修正: `as2_motion_reference_handlers` のSciPy実行時依存とPixiの対応付け
- 実行環境: Ubuntu 22.04.5 LTS / Linux x86_64、glibc 2.35、Pixi 0.81.0
- lockで選択されたJazzyのPython: 3.12.14

Ubuntu 24.04もPixiホストの利用対象ですが、24.04ホストでのビルド・回帰テストと
Ubuntu 24.04ベースのDocker経路は未実行です。

## 検査結果

| 項目 | 結果 |
|---|---|
| 提供パッチの適用検査 | 成功 |
| 設定・実行ガードの静的pytest | 17件合格 |
| 31個のPixi manifestとローカル依存先の整合性 | 合格 |
| 追加・更新したCI YAML、シェル、Pythonの構文 | 合格 |
| Pixiによるmanifest読込・Jazzy/Humbleチャンネル分離 | 合格 |
| 全4環境・3プラットフォームの依存解決 | 成功、`pixi.lock`生成 |
| Linux x86_64のJazzy全30パッケージビルド | 成功 |
| SciPy修正後のjazzy-tests環境のインストール | 成功 |
| `jazzy-check`（jazzy-tests環境） | 30パッケージ、Python API、CDR変換すべて合格 |
| 通信タイムアウトの単体テスト | 11件合格（0.14秒） |
| 静的17件 + ROS20件 + 通信11件の回帰テスト | 48件合格（ROS 11.15秒） |
| 既定Jazzy環境のインストール・`jazzy-check` | 成功・合格 |
| 既定環境の `ros2 pkg prefix` / `ros2 run` / `ros2 launch` CLI | 合格 |
| 統合パッチの上記上流コミットへの `git apply --check` と適用後の差分一致 | 合格 |

上流の子manifestにはTOML 1.1の複数行inline tableが含まれます。
全manifestの独立した構文検査にはtomli 2.4.1を使用しました。
Python 3.12標準のtomllibでは子manifestの一部を解析できませんが、
Pixi 0.81.0は読み込めます。

依存解決時に複数プラットフォームの `ros2-distro-mutex` キャッシュハッシュ不一致の
警告が出ましたが、再取得後にlock生成は完了しました。

初回の全パッケージビルドは成功しましたが、`jazzy-check` で
`drone_interface_teleop` のimportが `ModuleNotFoundError: scipy` になりました。
利用元である `as2_motion_reference_handlers/package.xml` に `python3-scipy` の
実行時依存を追加し、子manifestでcondaの `scipy` に対応付けました。

上流の軌道生成プラグインはCMake FetchContentで外部Gitリポジトリを取得します。
一部は `main` を参照するため、`pixi.lock` はこの外部ソースまで固定しません。
今回取得されたコミットは次のとおりです。

| ライブラリ | コミット |
|---|---|
| dynamic_trajectory_generator | `420700f2bc7ff14fdce1b13bf367baa23ad5adf7` |
| gcopter_trajectory_generator_lib | `4a1b4c080a4500fb4b5f13f2fbfc44fe391d42d4` |
| mav_trajectory_generation_lib | `65df05b537fdcb0b2a361b583bd37ae156578341` |

## GitHub Actionsのfork対応（2026-09-18）

forkへのpush後、上流から引き継いだ`docker-nightly`のDocker Hubログインが
`Username and password required`で失敗したとの報告を受け、公開ジョブの条件を修正しました。

- `docker-nightly`と`docker-release`の公開ジョブは、
  `github.repository == 'aerostack2/aerostack2'`の場合だけ実行します。
  `myamazum/aerostack2-jazzy`と他のforkではスキップします。
- Docker用ワークフロー3件のActionsをNode.js 24対応版へ更新しました。
  `checkout@v6`、`login-action@v4`、`setup-buildx-action@v4`、
  `setup-qemu-action@v4`、`build-push-action@v7`を各利用箇所に適用しています。
- 変更したDocker用ワークフロー3件は`actionlint 1.7.12`で合格し、
  全8件のワークフローはYAML解析に成功しました。
- 公開ジョブの条件を上流・このfork・別のforkについて確認しました。
  ビルド・テスト用ワークフローにDocker Hub公開用ログインや認証情報の参照がないことも確認しました。

この修正ではGitHub上のワークフローやDockerビルドは再実行していません。
公開ジョブのスキップはJazzy/Pixiのビルド・テスト成功を意味しません。
各バッジは、それぞれのワークフローの実行結果で判断してください。

## ライセンス・帰属表記の確認

2026-09-18に、このforkのソース差分と統合パッチを対象として、
上流の [BSD-3-Clauseライセンス](../../LICENSE) の保持を確認しました。

- ルートと各パッケージの既存`LICENSE`計5件は、上記上流コミットと同一です。
- 変更したPythonハンドラーの元の著作権・著者・ライセンス表記は保持しています。
- 日英READMEで上流の著者とforkの作者・メンテナーmyamazumの貢献範囲を区別し、
  上流による推奨・公認を示すものではないことを明記しています。
- fork独自の追加部分と統合パッチもBSD-3-Clauseで提供する旨を明記しています。
  再配布時の通知保持とバイナリへの通知添付については
  [CONTRIBUTING.md](../../CONTRIBUTING.md) に記載しています。

この確認範囲では、元のライセンス条件との不整合は見つかりませんでした。
依存ライブラリのコード・ビルド成果物は今回の追加ファイルと統合パッチに含めていません。
それらは個別のライセンスに従い、将来バイナリやDockerイメージを配布する場合は、
配布に含まれる依存ライブラリの通知要件も別途確認する必要があります。

## 再実行

apt版ROSをsourceしていないシェルでリポジトリルートから実行します。

```bash
pixi install --locked -e jazzy
pixi run --as-is -e jazzy jazzy-check
pixi install --locked -e jazzy-tests
AS2_TEST_DOMAIN_ID=71 pixi run --as-is -e jazzy-tests jazzy-test
```

71は未使用のROS domainを選ぶ例です。テスト結果は `test-results/` に保存されます。
Pixi経由のテストは追加のPython/ROSプロトコル回帰です。
上流C++のcolcon/CTest一式、Gazeboでの飛行、GUI、実機、Humbleと他CPU/OS上の
実行結果とは区別してください。

ROS回帰テストは既定RMW（`rmw_fastrtps_cpp`）で実行しました。
lark由来のPython非推奨警告が2件ありましたが、
テスト失敗はありません。JUnit結果は `test-results/jazzy/regression.xml` に保存しています。
通信タイムアウト単体テストのログは `test-results/jazzy/communication-timeouts.txt` に保存しています。
この作業環境に取得したPixi実行ファイルは
`/home/myamazum/work-ai/.tools/as2-pixi/pixi` です。
ビルド・インストール・実行確認のログは `test-results/jazzy/` に保存しています。
