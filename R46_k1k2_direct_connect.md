# R46: K1/K2 Direct Connect Patch for upstream.py
#
# 修改 upstrea.py 中的 _try_tier_keys 函数:
# - key_idx 0/1 (K1/K2): 直连 integrate.api.nvidia.com, 不用 SOCKS5
# - key_idx 2/3/4 (K3/K4/K5): 保持现有 SOCKS5 mihomo 代理
#
# 修改点:
#   1. 在 _make_nvcf_proxy_conn 后插入 _make_direct_conn 辅助函数
#   2. 在 _try_tier_keys 的 conn 创建行 (L285) 分叉
#   3. 日志行 (L270-271) 显示 direct vs SOCKS5
#
# 部署后验证:
#   1. docker restart hm40006
#   2. 抓包确认 K1/K2 的 TCP 连接目标地址是 integrate.api.nvidia.com:443
#      (不是 mihomo 7894/7895)
#   3. 查询 DB: K1/K2 的 429 率是否与 K3/K4/K5 不同