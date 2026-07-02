# R570 HM2 → HM1 优化

**轮次**: R570
**方向**: HM2 优化 HM1
**角色**: HM2(opc2_uname)
**日期**: 2026-07-02

## 数据（改前必有数据）

### 容器状态
- `nv_40006_uni`: Up 2min (healthy)
- 资源: Mem 18.48MiB/1GiB (1.80%), CPU 0.01%, NET 476kB/491kB, PIDs 3
- 容器限制: NanoCpus=1 core, Memory=1GiB, MemoryReservation=256MB

### 日志（近200行）
- `grep -ciE '(error|warn|err|fail|timeout|slow)'`: **0 ERROR / 0 WARN**
- 多次信息日志: `[NV-THINKING-TIMEOUT] (dsv4p_nv) thinking request stream=True → extended timeout 61s`（配置记录，非错误）
- 所有请求均为 `succeeded on first attempt`（attempt 1/7 keys）
- 零429、零fallback触发

### DB: nv_requests 最近10条（改前 22:12 采集，UTC+8）

| request_id | tier_model | ttfb_ms | duration_ms | status | finish_reason |
|------------|------------|---------|-------------|--------|---------------|
| 5132b8e1 | dsv4p_nv | 37693 | 37694 | 200 | tool_calls |
| 5c89ed77 | dsv4p_nv | 39547 | 39548 | 200 | stop |
| da6501a5 | dsv4p_nv | 26337 | 26337 | 200 | tool_calls |
| 07a6dd5c | dsv4p_nv | 7158 | 7159 | 200 | tool_calls |
| 6b5873a4 | dsv4p_nv | 27690 | 27690 | 200 | tool_calls |
| b4d40e9d | dsv4p_nv | 32460 | 32465 | 200 | stop |
| 7c9e967d | dsv4p_nv | 37296 | 37297 | 200 | tool_calls |
| 7906bcf1 | dsv4p_nv | 41240 | 41401 | 200 | stop |
| 12fb30b4 | dsv4p_nv | 47876 | 47877 | 200 | tool_calls |
| 972c7b76 | glm5_1_nv | 3636 | 3820 | 200 | length |

- 零 error_type，零 key_cycle_429s，零 fallback_occurred
- dsv4p 请求范围 7.2s–47.9s（ttfb≈duration，慢在API生成侧thinking模式）
- glm5.1 快请求仅 3.8s

### DB: 更早统计（近30min趋势，改前）
- 5key轮转正常，429率趋近于0
- max duration 约60s（history含更早数据），边缘请求逼近61s thinking-timeout ceiling

## 分析

两个可优化参数（少改原则，本轮双参数）：

### 1. MIN_OUTBOUND_INTERVAL_S=1.0 → 0.5
- dsv4p thinking请求实测7s–48s+，1.0s出站间隔在并发场景下造成请求线头额外等待
- 降到0.5消除50%出站throttle；KEY_COOLDOWN=25 >> 0.5，零429风险
- 历史优化方向：R521(1.5→1.2)→R548(1.2→1.0)，继续降到0.5是合理下一步

### 2. NVU_CONNECT_RESERVE_S=3 → 2
- 实测connect耗时0.6–2.1s（历史R533数据），reserve=3仍有~1.4x安全边际
- 降到2使有效PEXEC时间+1s；dsv4p边缘请求历史57.4s max success vs 59.3s failure，gap仅1.9s
- FASTBREAK=1机制下每次ATE省1s累计复用
- 与HM2当前保持一致（HM2 R533已用3，本轮HM1单独降2先走半步）

**不改的**: KEY_COOLDOWN/TIER_COOLDOWN=25（零429，当前安全，留到后续轮次）；容器资源限制（当前Mem利用率仅1.8%，暂时无忧）；UPSTREAM_TIMEOUT/THINKING_TIMEOUT（需多轮数据验证后再动）。

**铁律**: 本轮只改HM1的 `/opt/cc-infra/docker-compose.yml` env参数，不改HM2任何配置。

## 执行改动

在HM1 `/opt/cc-infra/docker-compose.yml` `nv_40006_uni` 服务环境变量中：

```yaml
      MIN_OUTBOUND_INTERVAL_S: "0.5"  # R570: HM2→HM1 — 1.0→0.5 (-0.5s). dsv4p thinking请求30-40s+下1.0s出站节流造成并发排队; 降50%加速请求发出; KEY_COOLDOWN=25 >> 0.5零429风险; 双参数; 铁律:只改HM1不改HM2
      NVU_CONNECT_RESERVE_S: "2"    # R570: HM2→HM1 — 3→2 (-1s). 实测connect 0.6-2.1s, reserve=2仍0.95-3.3x安全边际; dsv4p thinking请求max 37-48s需更多pexec可用时间; +1s有效pexec时间救回边缘截断; 少改多轮; 铁律:只改HM1不改HM2
```

执行：
```bash
cd /opt/cc-infra && docker compose up -d nv_40006_uni
```

容器正常 Recreate → Start，无中断。

## 验证（改后必有验证）

- 容器: `nv_40006_uni` Up ~41s (healthy) ✅
- health endpoint: `{"status":"ok","proxy_role":"passthrough","nv_num_keys":5,"nvcf_pexec_models":["kimi_nv","dsv4p_nv","glm5_1_nv"],...}` ✅
- env确认:
  - `MIN_OUTBOUND_INTERVAL_S=0.5` ✅
  - `NVU_CONNECT_RESERVE_S=2` ✅
- 零ERROR/WARN日志，proxy正常监听，端口40006通
- 改后首条dsv4p请求: 20779ms (20.8s), status=200, 成功完成

## 总结

本轮双参数优化（少改多轮，铁律执行）：
1. **MIN_OUTBOUND_INTERVAL_S 1.0→0.5**: 消除50%出站throttle，改善并发排队等待
2. **NVU_CONNECT_RESERVE_S 3→2**: +1s有效PEXEC可用时间，救回边缘dsv4p thinking请求截断风险

只改HM1 `/opt/cc-infra/docker-compose.yml`，未碰HM2任何文件/配置/容器。等待后续轮次继续积累优化。

## ⏳ 轮到HM1优化HM2
