# Jazzy用の既定設定と回帰テスト

対象: `aerostack2/aerostack2` の main、コミット
`19c397309c6a41b279e6b551818ec12605cfcecc`（2026-09-17に取得した参照）。

## 対応範囲

このforkはmyamazumが管理し、Ubuntu 22.04および24.04上でPixi / RoboStackを使って
ROS 2 Jazzy版のAerostack2を利用することを目的としています。既存のUbuntu 22.04環境でも
利用できるようにすることが主要な動機です。実際のビルド・回帰検証はUbuntu 22.04.5で
実施しており、Ubuntu 24.04ホスト上ではまだ実施していません。
配布する [統合パッチ](../../patch/aerostack2-jazzy-r2.patch) の適用先は上記の
上流mainのコミットです。別途用意しているDocker経路はUbuntu 24.04を使いますが、
今回のローカル検証では実行していません。

上流mainには既にJazzy用CI、Dockerfile、Pixi環境があります。この差分は
移植済みC++コードを置換するものではなく、ローカル環境の既定値をJazzyへ変更し、
テストを補うものです。Humbleの明示指定環境と上流のHumble/Jazzy CIは残します。

提供パッチの作成時点では静的検査のみが実施されていました。
このリポジトリでの追加実装・検証結果は [検証記録](VERIFICATION.md) に記載します。

`as2_platform_crazyflie`、CrazySim、MuJoCo、cflibのソースはこの差分に含みません。
上流のJazzy準備Issue #852とJazzy CIではCrazyflieプラットフォームが未完了/TODOです。
このパッチだけで既存のCrazySim複数機環境がAS2へ接続されるわけではありません。

## Pixi / RoboStack

Humbleやapt版ROSをsourceしていない新しいシェルで実行してください。
Pixi 0.81.0以上が必要です。CIは0.81.0に固定しています。
AS2ルートのmanifestを明示し、親の`drone_ws/pixi.toml`や別の子manifestを
誤って選択しないようにします。

```bash
AS2=/absolute/path/to/aerostack2
pixi install --manifest-path "$AS2/pixi.toml" -e jazzy
pixi run --as-is --manifest-path "$AS2/pixi.toml" -e jazzy jazzy-check
pixi run --as-is --manifest-path "$AS2/pixi.toml" -e jazzy python -c \
  'import os,sys,rclpy; print(os.environ.get("ROS_DISTRO"),sys.executable,rclpy.__file__)'
```

上流のroot manifestは、`aerostack2 = { path = "./aerostack2" }` と
pixi-buildを使う構成です。したがって、ここでの`pixi install`にはローカルパッケージの
ビルドが含まれ得ます。通常のcolconワークスペースと同一の`build/`ができるとは限りません。
Pixiでinstallしただけの状態に、rootの`colcon test`を実行しても
上流C++テストを実行した証拠にはなりません。

環境の既定値もJazzyなので、リポジトリルートでは `pixi install` と
`pixi run --as-is jazzy-check` だけでも同じ確認ができます。`jazzy-check` はROSノードを
起動せず、全AS2パッケージのament登録先、Python APIのimport先、生成action型の
CDR往復変換を確認します。`ros2 run` / `ros2 launch` のCLIも明示的に導入します。
既存の `pixi-build.yaml` CIにこの確認とLinux x86_64上のPixi回帰テストを追加しています。
`--as-is` はインストール済み環境を更新せず実行します。ソースや依存を変更した場合は、
先に対象環境の `pixi install` を実行してください。

PixiのROSパッケージビルド手順:
https://pixi.prefix.dev/latest/build/ros/
RoboStackの環境構築上の注意:
https://robostack.github.io/GettingStarted.html

追加のROS回帰テスト:

```bash
pixi install --manifest-path "$AS2/pixi.toml" -e jazzy-tests
# 71が実験設備・他のテストで使われていないことを確認して指定する。
AS2_TEST_DOMAIN_ID=71 AS2_TEST_RESULTS_DIR=/tmp/as2-jazzy-pixi-results \
  pixi run --as-is --manifest-path "$AS2/pixi.toml" -e jazzy-tests jazzy-test
```

この経路は、そのPixi環境で選択されているRMWで実行します。Cyclone DDSを含む
2種類のRMW比較は、下記Docker/apt CIで明示的に実施します。Pixi環境への
両方のDDS実装の導入・解決確認までは本パッチで行っていません。
ルートの `pixi.lock` はPixi 0.81.0で生成し、Gitの保存対象にしています。
同じ解決結果を使用する場合は `pixi install --locked -e jazzy` を実行してください。

## Docker / Ubuntu 24.04 + Jazzy

リポジトリルートで、ローカルソースから2段階でビルドします。
公表済みのAS2 Jazzyイメージが存在することは前提にしません。

```bash
cd "$AS2"
docker build --build-arg BUILD_TESTING=ON \
  -f docker/jazzy/Dockerfile -t as2-jazzy-under-test:local .
docker build -f docker/jazzy/Dockerfile.regression \
  -t as2-jazzy-regression:local .

for RMW in rmw_fastrtps_cpp rmw_cyclonedds_cpp; do
  mkdir -p "$AS2/test-results/$RMW"
  docker run --init --rm \
    -e RMW_IMPLEMENTATION="$RMW" \
    -e AS2_TEST_DOMAIN_ID=71 \
    -e AS2_TEST_RESULTS_DIR=/test-results \
    -v "$AS2/test-results/$RMW:/test-results" \
    --entrypoint /bin/bash as2-jazzy-regression:local \
    -c 'bash "$AEROSTACK2_PATH/scripts/jazzy/run_ci.sh"' || exit 1
done
```

`run_ci.sh`は、既存のcolconテストと追加のpytestテストを実行します。
既存テストが失敗しても、追加テストの実行を試みたうえで最終的に非ゼロを返します。
JUnit XMLと既存テストの要約を保存します。GUI・GPU・機体は必要ありません。

追加のGitHub Actions `jazzy-regression.yaml` は、この手順を両RMWで実行します。
上流の`build-jazzy.yaml`と`build-humble.yaml`は変更していません。
ベースDockerイメージ、aptパッケージ、GitHub Actionsは完全な版固定ではありません。
認定用記録にはDocker digest、`dpkg-query -W`、RMW設定も保存してください。

## 追加テストで確認する内容

| テスト | 確認する範囲 | 確認しない範囲 |
|---|---|---|
| source/configuration | Jazzy既定値、Humble環境維持、rosdep失敗扱い | インストール・ビルド成功 |
| runner guard | 未指定/不正domain、Humble環境の拒否 | 通信隔離そのものの形式的保証 |
| import/CDR | AS2 Python APIのimport、生成msg/action/service型の往復変換 | すべてのAS2メッセージの網羅 |
| 2機状態受信 | 実際のDroneInterfaceBaseの名前空間、BEST_EFFORT状態受信、状態混線防止 | C++状態推定器・実際のTFツリー |
| arming | 実際のAS2 APIから模擬SetBoolサービスへの振分け、2機同時呼出し | 実機のarming・安全停止 |
| clock | AS2ノードのROS時刻の進行・停止・後退 | C++制御器の時刻後退処理 |
| BehaviorHandler | 模擬Takeoff actionへのgoal、feedback、成功・拒否・中断結果、pause/modify/resume/stopサービス | C++ BehaviorServer、ROS cancel_goal、飛行制御・姿勢応答 |

Ubuntu 22.04 / Linux x86_64のPixi環境では、静的17件・追加ROS20件・
通信タイムアウト単体11件の計48件が合格しました。
実行環境・依存修正は [検証記録](VERIFICATION.md) を参照してください。
テストはAS2の実コードを呼びますが、相手は模擬ROSエンドポイントです。
特にstopサービスの確認を、ROS actionのcancel_goal確認と同一視しないでください。

テストは一意な名前空間を生成し、無線・UDP機体接続は使用しません。
ただし`/clock`はdomain内で共有されるため、専用の未使用domainを指定してください。
`run_regression.sh`は意図しない待機をpytest-timeoutで打ち切ります。
加えて、`ServiceHandler`と`BehaviorHandler`の単体テストを実行し、サービス不在・
サービス応答停止・goal応答停止・status/feedback途絶・IDLE後のresult未着を確認します。

## 通信タイムアウト

`ServiceHandler` は、サービスの利用可否と応答を各3秒で打ち切り、
`ServiceNotAvailable` または `ServiceCallTimeout` を送出します。
`BehaviorHandler` も goal 応答・pause/resume/stop/modify 応答を期限付きにし、
アクティブなbehaviorからstatus/feedbackが3秒途絶えた場合は
`BehaviorCommunicationLost` を送出します。IDLE通知後にaction resultが届かない場合も
3秒で `ResultResponseTimeout` を送出します。goal応答が遅れて届いた場合は、
安全のため受理済みgoalのcancelを試行します。

これらは通信待機を無期限にしないためのAPI上の終了条件です。実機接続での再接続、
watchdog、フェイルセーフ動作そのものを実装・認定するものではありません。

次の試験は別途必要です: C++ lifecycle/TF/pluginlib、上流制御器と状態推定器の
起動・停止、Humble回帰ビルド、Gazebo Harmonic起動、CrazySim接続アダプタの
単位・座標系・時刻・watchdog、単機と複数機のSITL、異常系、GUI。
これらは今回のPixi環境確認と追加のプロトコル回帰テストの対象外です。

## 上流の確認資料

- https://github.com/aerostack2/aerostack2/commit/19c397309c6a41b279e6b551818ec12605cfcecc
- https://github.com/aerostack2/aerostack2/blob/19c397309c6a41b279e6b551818ec12605cfcecc/.github/workflows/build-jazzy.yaml
- https://github.com/aerostack2/aerostack2/blob/19c397309c6a41b279e6b551818ec12605cfcecc/pixi.toml
- https://github.com/aerostack2/aerostack2/blob/19c397309c6a41b279e6b551818ec12605cfcecc/docker/jazzy/Dockerfile
- https://github.com/aerostack2/aerostack2/issues/852
- https://github.com/aerostack2/aerostack2/blob/19c397309c6a41b279e6b551818ec12605cfcecc/as2_python_api/as2_python_api/service_clients/service_handler.py
- https://github.com/aerostack2/aerostack2/blob/19c397309c6a41b279e6b551818ec12605cfcecc/as2_python_api/as2_python_api/behavior_actions/behavior_handler.py
