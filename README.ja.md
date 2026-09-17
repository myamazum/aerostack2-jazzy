[English](README.md) | **日本語**

[![arXiv](https://img.shields.io/badge/arXiv-2303.18237-b31b1b.svg)](https://arxiv.org/abs/2303.18237) [![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](https://opensource.org/licenses/BSD-3-Clause) [![Build Status ROS2 Package](https://build.ros2.org/job/Hbin_uJ64__aerostack2__ubuntu_jammy_amd64__binary/badge/icon)](https://build.ros2.org/job/Hbin_uJ64__aerostack2__ubuntu_jammy_amd64__binary/) [![codecov_test](https://github.com/aerostack2/aerostack2/actions/workflows/codecov_test.yaml/badge.svg)](https://github.com/aerostack2/aerostack2/actions/workflows/codecov_test.yaml) [![humble](https://github.com/aerostack2/aerostack2/actions/workflows/build-humble.yaml/badge.svg)](https://github.com/aerostack2/aerostack2/actions/workflows/build-humble.yaml) [![Pixi Badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/prefix-dev/pixi/main/assets/badge/v0.json)](https://pixi.sh)

# Aerostack2 — aerostack2-jazzy fork

Aerostack2 は、複数の飛行ロボットによる自律システムの開発を容易にする ROS 2 フレームワークです。

## この fork について（myamazum による追記）

このリポジトリ [myamazum/aerostack2-jazzy](https://github.com/myamazum/aerostack2-jazzy) は、
[Aerostack2](https://github.com/aerostack2/aerostack2) を元にした fork とパッチ集で、
[myamazum](https://github.com/myamazum) が管理しています。
Humble を基盤とする Aerostack2 の利用環境を更新し、既存の Ubuntu 22.04 環境を含む
**Ubuntu 22.04／24.04 上で、Pixi / RoboStack を通じて ROS 2 Jazzy を利用する**ことが目的です。
この fork では、Jazzy の既定化、依存関係の修正、通信タイムアウト、回帰テストを追加しています。
ビルドと回帰テストは Ubuntu 22.04.5 で実施済みです。Ubuntu 24.04 も利用対象ですが、
同ホスト上での動作は未検証です。

### fork のパッチを上流 main に適用する

[統合パッチ](patch/aerostack2-jazzy-r2.patch) には、この fork で管理する追加・修正が含まれます。
対象は Pixi/Jazzy 設定と lock ファイル、依存関係の修正、通信タイムアウト、テスト、CI、
ドキュメントです。以前の Jazzy 対応パッチと通信タイムアウトパッチは統合済みなので、
適用するパッチはこの1件です。ビルド成果物とローカルのテストログは含みません。

適用先は上流 `main` のコミット
[`19c397309c6a41b279e6b551818ec12605cfcecc`](https://github.com/aerostack2/aerostack2/commit/19c397309c6a41b279e6b551818ec12605cfcecc)
です。この上流コミットには、既に Jazzy 用 CI、Dockerfile、Pixi の `jazzy` 環境が含まれています。
この fork は、それらの既存の対応を基に追加修正を行っています。
パッチは、このコミットをチェックアウトした未変更の作業ツリーへ適用してください。
それより新しい上流コミットでは、パッチの調整が必要になる場合があります。

上記コミットの作業ツリーで、ダウンロードしたパッチを次のように適用します。

```bash
git apply --check /absolute/path/to/aerostack2-jazzy-r2.patch
git apply /absolute/path/to/aerostack2-jazzy-r2.patch
```

この fork のソースには、既にパッチの変更が反映されています。
Pixi を使うホストは Ubuntu 22.04／24.04 を想定し、別途用意した Jazzy 用 Docker 経路は
Ubuntu 24.04 を使います。Docker 経路は今回のローカル検証では実行していません。
[Jazzy の公式 Ubuntu バイナリ](https://docs.ros.org/en/jazzy/Installation/Alternatives/Ubuntu-Install-Binary.html)
は Ubuntu 24.04 を対象としていますが、この fork では Pixi 環境内に RoboStack から Jazzy を導入します。
Humble も `pixi run -e humble ...` や Humble 用 Docker タスクで利用できます。

この fork は上流 Aerostack2 プロジェクトとは独立して管理しています。
冒頭のビルド・カバレッジバッジは上流の結果を示します。
この fork 固有の結果は [検証記録](docs/jazzy/VERIFICATION.md) を参照してください。

確認手順とプラットフォームごとの未完了項目は
[Jazzy のセットアップと回帰テスト](docs/jazzy/README.md) に記載しています。
この fork で Jazzy を既定化したことは、飛行試験の完了や公式 Jazzy リリースを意味しません。

## Pixi / ROS 2 Jazzy（fork のセットアップ）

Pixi 0.81.0 以上を使用してください。apt 版 ROS のセットアップを source していないシェルで、
このリポジトリのルートから実行します。

```bash
pixi install
pixi run --as-is jazzy-check
pixi run --as-is ros2 pkg prefix as2_core
pixi shell
```

`pixi install` は `pixi-build-ros` でローカルの Aerostack2 パッケージをビルドし、
RoboStack から ROS 2 Jazzy を導入します。`ros2 run` と `ros2 launch` も含まれます。
環境を明示する場合は `-e jazzy` を指定できます。回帰テストは次の手順で実行します。

```bash
pixi install -e jazzy-tests
AS2_TEST_DOMAIN_ID=71 pixi run --as-is -e jazzy-tests jazzy-test
```

テストには未使用の ROS domain を指定してください。
詳しくは [セットアップ・検証手順](docs/jazzy/README.md) を参照してください。

1.0.9 より前のバージョンは ROS 2 Galactic（Ubuntu 20.04）でも開発・検証されており、
`EOL/galactic` ブランチにあります。

Jazzy 用の Docker イメージは、この作業ツリーから
`docker compose -f docker/compose.yaml build jazzy` でビルドします。
この手順はローカルソースを対象とし、公開済みの `aerostack2/jazzy` イメージを前提としません。
既存の Humble イメージは [Aerostack2 Dockerhub](https://hub.docker.com/u/aerostack2) にあります。

主な特徴:

- ROS 2 を基盤とした設計。
- 各要素を独立して変更・交換できるモジュール構成。
- 飛行プラットフォームに依存せず、シミュレーションから実機へ移行しやすい構成。
- プロジェクトに必要なパッケージだけを導入・利用できる構成。
- 複数機の協調動作を考慮した設計。

全体の説明は [Aerostack2 公式ドキュメント](https://aerostack2.github.io) を参照してください。

上流のインストール手順は
[こちら](https://aerostack2.github.io/_00_getting_started/index.html#ubuntu-debian) にあります。

<br />

https://user-images.githubusercontent.com/35956525/231999883-e491aa08-2835-47a9-9c68-5b2936e8594e.mp4

<br />

# クレジット

Aerostack2 は上流の著者・コントリビューターによって開発されました。
元のクレジット、ソース内の著作権表記、[BSD-3-Clause ライセンス](LICENSE) を保持しています。

**この fork の作者・メンテナー: [myamazum](https://github.com/myamazum)。**
ここで記載する貢献は、Ubuntu 22.04 を含む Ubuntu ホスト向けの Pixi / Jazzy 対応、
依存関係と通信タイムアウトの修正、追加テスト、ドキュメント、統合パッチの保守です。
この fork または上流への貢献については [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

統合パッチを含む、この fork 独自の追加部分も [BSD-3-Clause ライセンス](LICENSE) で提供します。
第三者のコードや依存ライブラリには、それぞれのライセンスが引き続き適用されます。
上流の著者への帰属表記は、著者によるこの fork の推奨・公認を意味しません。

学術目的でコードを利用する場合は、以下の上流の論文を引用してください。

* M. Fernandez-Cortizas, M. Molina, P. Arias-Perez, R. Perez-Segui,
D. Perez-Saura, and P. Campoy, 2023, ["Aerostack2: A software framework for
developing multi-robot aerial systems"](https://arxiv.org/abs/2303.18237), ArXiv DOI 2303.18237.
