# Crazyswarm2機能差分とAerostack2への追加候補

更新日: 2026-10-06

比較基準は `IMRCLab/crazyswarm2` main の
`f1e09954f56cd08e7d9aff5e13dc9a68795914a3`（2026-09-11）です。

ここで「Aerostack2にない」とする機能は、Aerostack2で同等の結果を構成できないという
意味ではありません。現在このforkで使用している汎用AS2 APIに、Crazyswarm2のような
fleet-levelまたはCrazyflie固有の第一級インタフェースがない、という意味です。

## 候補一覧

| 優先度 | 候補 | Crazyswarm2側 | 現在のAS2との差 | 実装場所の候補 |
|---|---|---|---|---|
| P0 | fleet registry / named group | `CrazyflieServer.crazyflies`, `crazyfliesByName` | Python APIは基本的に機体namespace単位 | 汎用fleet層 |
| P0 | selected/all機体への一括操作 | `all/takeoff`, `all/land`, `all/go_to`, `all/arm` | 各namespaceへの呼出しは可能だがfleet APIがない | 汎用fleet層 |
| P0 | fleet状態集約 | serverが全Crazyflieを保持 | `DroneInterfaceBase` は1機単位 | 汎用fleet層 |
| P0 | 多数機operator UI | swarm APIを前提とした操作 | このforkにはブラウザfleet consoleがない | `as2_user_interfaces` |
| P1 | firmware group mask | `SetGroupMask.srv`, 各serviceの `group_mask` | 汎用AS2に相当概念なし | Crazyflie platform拡張 |
| P1 | radio-level broadcast | `all/*` のbroadcast/group処理 | AS2側fan-outはradio broadcastではない | `crazyflie_cpp` + platform拡張 |
| P1 | Crazyflie health/status | battery, PM state, supervisor flags, RSSI, latency, packet counters | `PlatformInfo` は汎用状態のみ | diagnostics adapter |
| P1 | connection statistics | sent/receive/enqueued/ACK/ping counters | 汎用AS2状態にはない | diagnostics adapter |
| P2 | firmware parameter管理 | `getParam`, `setParam`, `UpdateParams`, `all.params.*` | 汎用vehicle API外 | CF管理API |
| P2 | dynamic firmware logging | `AddLogging`, `RemoveLogging`, `LogDataGeneric` | Crazyflie TOC logging相当なし | CF管理API |
| P2 | onboard polynomial trajectory | `UploadTrajectory`, `StartTrajectory`, timescale/reverse/relative | AS2 trajectory behaviorとは実行場所・意味が異なる | CF trajectory adapter |
| P2 | low/high-level setpoint handover | `NotifySetpointsStop` | 直接対応する汎用operator primitiveなし | CF platform拡張 |
| P3 | full-state command broadcast | `all/cmd_full_state` | AS2 control interfaceはあるがCF broadcast primitiveではない | 必要時のみ検討 |

## 今回実装したP0

`as2_user_interfaces/as2_swarm_web_ui` を追加し、以下を実装しました。

1. 明示設定またはROS graph discoveryによるfleet registry
2. named groupとcheckboxによる任意機体選択
3. arm/disarm、offboard/manual、takeoff、land、GoToの一括要求
4. `PlatformInfo`、pose、twistの集約表示とstale判定
5. emergency hover / emergency land / 二重確認付きkill switch
6. 外部CDN、rosbridge、追加web frameworkを必要としないHTML UI
7. host側の要求送出時間差 `dispatch_span_ms` の記録

このP0は `as2_platform_crazyflie` に依存しないため、同じAS2 endpointを持つPX4等にも
利用できます。

## 同期に関する境界

今回のgroup commandは、対象namespaceへ短時間にROS 2要求を送る
**concurrent fan-out**です。Crazyswarm2/Crazyradioのradio-level broadcastではなく、
同時開始を保証しません。

`dispatch_span_ms` はbridgeが各ROS要求をsubmitした時間差だけを測定します。
DDS scheduling、platform処理、transport、firmware受信、実際の運動開始の差は含みません。

実験でfirmware側の共通radio eventによる開始が必要になった場合は、P1として次の構成を
追加するのが適切です。

```text
HTML / fleet API
       |
Aerostack2 generic group operation
       |
       +-- normal backend: per-namespace ROS fan-out
       |
       `-- Crazyflie capability: group mask + radio broadcast
                                  |
                              crazyflie_cpp
                                  |
                         radio or UDP/SITL transport
```

この構成なら、現在の `as2_platform_crazyflie` とCrazySim/UDP経路を維持したまま、
broadcastをoptional capabilityとして追加できます。

## 次の実装順

1. **Crazyflie health / connection diagnostics**  
   RSSI、unicast latency、packet/ACK counters、battery、supervisor stateをfleet UIへ集約。
   飛行コマンドを変更せず評価できるため、次に実装しやすい項目です。
2. **group mask + true radio broadcast**  
   host fan-outで不足する場合に追加し、command arrival/start skewを計測して評価します。
3. **firmware parameter / logging管理**  
   10～20台を同一条件に設定し、同一形式でログ取得する用途に有用です。
4. **onboard trajectory upload/start**  
   hostから連続setpointを送るよりfirmware内trajectory実行が適する実験で追加します。
5. **setpoint handover / full-state broadcast**  
   low-level streaming制御とhigh-level commanderを切り替える実験が必要な場合のみ追加します。

## Crazyswarm2で確認した主な実装

- `crazyflie_py/crazyflie_py/crazyflie.py`
- `crazyflie_interfaces/srv/SetGroupMask.srv`
- `crazyflie_interfaces/srv/UploadTrajectory.srv`
- `crazyflie_interfaces/srv/StartTrajectory.srv`
- `crazyflie_interfaces/srv/AddLogging.srv`
- `crazyflie_interfaces/srv/RemoveLogging.srv`
- `crazyflie_interfaces/srv/NotifySetpointsStop.srv`
- `crazyflie_interfaces/msg/Status.msg`
- `crazyflie_interfaces/msg/ConnectionStatistics.msg`
