# 已归档:双机交替优化机制 (2026-07-02 停用)

本目录的脚本是 R314~R569 期间"双机交替优化"机制的载体,**现已停用**。

## 为什么停用
用户决定取消"只改对端 / 互相改"规则,改由 Claude Code 直接维护两机。
- 自动轮询(systemd timer / cron)在 R569 框架清理时已停
- 规则层面:见仓库根 `rule.md` / `README.md`,已删除"只改对端""每轮少改"条目
- 详见 memory: `alt-optimize-auto-exec-2026-06-30` 等

## 脚本说明(仅作历史追溯,勿再激活)
- `watch_and_next.sh` — 每 1min poll 远程仓库,检测"非本机提交 + 轮到我了"标记 → 写 trigger 通知
- `run_my_turn.sh` — 被 watch 触发,起 claude 非交互 session 自动改对端 + commit + push + 翻轮

## 如需恢复
恢复需同时:重新 enable systemd timer(HM1 `hermes_alt_optimize.timer` / HM2 同名)+
恢复 `rule.md` 的"只改对端"条目 + 把本目录脚本 `git mv` 回 `scripts/`。
**不建议恢复** — 交替机制历史上反复出现同号撞车、孤儿 session、角色错乱等问题
(见 memory: r350/r354/r361/r380 等),直接维护更稳。
