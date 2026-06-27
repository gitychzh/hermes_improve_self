# HM2 新框架上游代码 — upstream.py 改动

# 核心改动: is_direct = True (所有 5 个 K 统一直连 NVCF API)
# 之前: is_direct = key_idx in [0, 1]  (只有 K1/K2 直连)
# 现在: is_direct = True  (所有 K 都为 DIRECT)

def _make_nvcf_request(...):
    # ...
    is_direct = True  # 所有 5 个 K 都为 DIRECT (直连 NVCF API)
    
    # 适用所有 K, 不需要 mihomo 代理
    # K1/K2/K3/K4/K5 统一使用:
    #   curl -X POST https://api.studio.nvidia.com/v1/chat/completions \
    #     -H "Authorization: Bearer $NVCF_KEY"
    #     -H "Content-Type: application/json"
    #     -d '{"model": "deepseek-ai/deepseek-v4-pro", ...}'
    
    # ...
    return response