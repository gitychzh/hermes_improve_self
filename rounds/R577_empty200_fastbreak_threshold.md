# R577: empty_200 FASTBREAK 语义改连续次数阈值 (修复 surge 期 143s 卡死)

## 背景

R576 修复了 dsv4p force-stream content 丢失,但 openclaw 在 NVCF surge 期仍会卡死。
深挖 01:32-01:35 的 empty_200 洪水:

```
01:32:44 NV-INTEGRATE-EMPTY k2 → 01:32:47 k5 success  (cycle 救回有效, 偶发)
01:34:07 NV-INTEGRATE attempt 1/7 k5 (stream=True msgs=35 openclaw)
01:34:14 NV-EMPTY-200 k5 content=null + NV-EMPTY-CYCLE  (pexec 路径)
01:34:14 NV-KEY attempt 2/7 k1 → pexec
01:34:17 NV-EMPTY-200 k1
... 7 连发 empty (k5→k1→k2→k3→k4→k5→k1) ...
01:35:00 NV-TIER-FAIL empty200=14 elapsed=143413ms  (143s!)
01:35:00 NV-PEER-FB → HM2 (peer 也 timeout, 同 surge)
01:35:25 peer fallback FAILED → 502 openclaw
```

## 根因

R567 把 `NVU_EMPTY_200_FASTBREAK` 从 1 改到 0 (禁用),理由是"empty200 后换 key 必败"被证伪
(偶发 empty cycle 救回有效)。但 R567 在 **NVCF surge 期**(全 5 key 连发 empty)有害:
- 每次 empty 要等 thinking timeout ~10-20s
- 7 次 cycle = 143s
- openclaw 等不了 143s → 卡死

R567 的偶发救回逻辑(1 次 empty→cycle→success)成立,但 surge 期连发 empty cycle 无效。

## 修复 (R577)

把 `NVU_EMPTY_200_FASTBREAK` 语义从 boolean 改为**连续次数阈值**:

| 值 | 语义 | 行为 |
|---|---|---|
| 0 | 禁用 | 全 cycle (R567 当前, surge 期 143s 卡死) |
| 1 | 每次 empty 都 break | R567 之前, 激进, 丢失偶发救回 |
| N≥2 | 连续 N 次 empty 才 break | **平衡: 1-2 次仍 cycle 救回, N+ 次连发 fastbreak** |

设 `NVU_EMPTY_200_FASTBREAK=3`:
- 偶发 empty (1-2 次): 继续 cycle 换 key, 保留 R567 的救回能力
- surge 期 (3+ 次连发): fastbreak, 3 次 cycle (~30-60s) 后 break, 省下后面 4 次 (~80s+)
- 成功/timeout 重置计数器

## 代码改动 (两机同步)

`gateway/upstream.py`:
- `_try_integrate_keys` (line ~143): 加 `consecutive_empty_200 = 0` 初始化
- `_try_integrate_keys` empty 处理 (line ~267): `consecutive_empty_200 += 1; if EMPTY_200_FASTBREAK > 0 and consecutive_empty_200 >= EMPTY_200_FASTBREAK: break`
- `_try_integrate_keys` 成功 (line ~282): `consecutive_empty_200 = 0` 重置
- `_try_tier_keys` (line ~441): 同上初始化
- `_try_tier_keys` empty 处理 (line ~617): 同上阈值判断
- `_try_tier_keys` 成功 (line ~632): 同上重置

`docker-compose.yml` (两机):
- `NVU_EMPTY_200_FASTBREAK: "0"` → `"3"` (HM1 line 469)
- HM2 新增 `NVU_EMPTY_200_FASTBREAK: "3"` (line 490, 之前 HM2 compose 无此 env, 用代码默认 1)

## 验证

- [x] HM1 代码: `grep -c consecutive_empty_200 upstream.py` = 10
- [x] HM2 代码: 同 10
- [x] HM1 env: `NVU_EMPTY_200_FASTBREAK=3`
- [x] HM2 env: `NVU_EMPTY_200_FASTBREAK=3`
- [x] HM1 health: ok
- [x] HM2 health: ok
- [x] HM1 端到端: openclaw "水沸腾温度" 正常返回
- [ ] HM1 真实 surge 触发验证 (待下次 NVCF surge 期观察 3 连发 empty 后是否 fastbreak)

## 预期效果

- 偶发 empty (1-2 次): 无影响, 仍 cycle 救回 (保留 R567 优点)
- surge 期 (3+ 连发): 3 次 cycle (~30-60s) 后 break, 比原来 7 次 (143s) 省 ~80s+
- break 后 fall through 到 pexec (integrate 路径) 或返回 502 (pexec 路径), peer fallback 接管

## 未解之谜 (不影响修复)

01:34:14 的 `NV-EMPTY-200 content=null` (pexec.py:105 非流分支) 与 stream=True 请求的矛盾:
- _check_empty_200(is_stream=True) 应走 stream 分支只查 CL=0
- content=null 日志只能从非流分支打出, 要求 is_stream=False
- 诊断 (NV-DIAG-EMPTY) 在成功路径显示 is_stream=True cl=-1 caller=execute_request
- 日志被清空后无法重新验证 01:34 失败案例
- 推测: surge 期 NVCF/integrate 可能对 stream=True 请求返回非流 200 (Content-Length 有值, body 可读, content=null), 但此推测未证实
- R577 的阈值机制不依赖此矛盾的解决: 无论 empty 怎么检测, 连续 3 次 break 都能止损
