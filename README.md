# Hermes 双机 hm-40006--nv 优化

> 维护模式(2026-07-02 起):取消"双机交替优化/只改对端"机制。
> 现由 Claude Code 直接维护两机,不再互相改、不再轮转角色(执行者/质疑者)。
> 自动轮询/执行脚本已归档,systemd timer/cron 在 R569 已停。

## 主机
- **HM1**: `opc_uname` @ `100.109.153.83` (ssh -p 222)
- **HM2**: `opc2_uname` @ `100.109.57.26` (ssh -p 222), hostname `opc2sname`

## 铁律 (见 `rule.md`)
- 改前必有数据 / 改后必有验证
- 聚焦 `hm-40006--nv` 链路(及其直接关联的 nv_40006_uni 网关)
- **CC 直接改两机** — HM1/HM2 均由 CC 直接编辑部署,无需通过对方执行
- 所有修改写入仓库

## 仓库结构
```
hermes_improve_self/
├── README.md
├── rule.md                         # 优化铁律
├── rounds/                         # 历史轮次记录(交替优化时期遗留, 命名 R<N>_hmX_optimize_hmY.md)
├── scripts/
│   ├── nvcf_func_monitor.py        # NVCF function 健康监控(每 10min, 仍活跃)
│   └── _archived_alt_optimize/     # 已停用的交替优化脚本(watch_and_next.sh / run_my_turn.sh)
├── deploy_artifacts/               # 每轮源码快照
└── docs/
```
