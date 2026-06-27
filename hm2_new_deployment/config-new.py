# HM2 完整新框架配置 — config.py (容器内代码)

# 模型定义
NV_MODEL_IDS = {
    "deepseek_hm_nv": "deepseek-ai/deepseek-v4-pro",
    "kimi_hm_nv": "moonshotai/kimi-k2.6",
}

# All 5 keys DIRECT (直连 NVCF API)
HM_NV_PROXY_URLS = [
    "",  # K1: DIRECT → NVCF API
    "",  # K2: DIRECT → NVCF API
    "",  # K3: DIRECT → NVCF API
    "",  # K4: DIRECT → NVCF API
    "",  # K5: DIRECT → NVCF API
]

# Tier 层级 (两阶: deepseek → kimi fallback)
HM_MODEL_TIERS = [
    "deepseek_hm_nv",
    "kimi_hm_nv",
]

# 默认模型
DEFAULT_NV_MODEL = "deepseek_hm_nv"

# 超时配置
UPSTREAM_TIMEOUT_S = 85  # per-key
TIER_TIMEOUT_BUDGET_S = 125  # whole tier
KEY_COOLDOWN_S = 35  # after 429
TIER_COOLDOWN_S = 78  # between tiers
MIN_OUTBOUND_INTERVAL_S = 13.5  # inter-request spacing

# NVCF url format
HM_NVCF_URL_FMT = "https://api.studio.nvidia.com/v1/chat/completions"

# Retry config
MAX_RETRIES_PER_KEY = 3
KEY_SWITCH_ON_429 = True
KEY_STICKY_ON_SUCCESS = True

# Tier management
ENABLE_TIER_FALLBACK = True
TIER_ATTEMPT_LIMIT = 7  # max attempts per tier before fallback
ROUND_ROBIN_MODE = True  # always cycle keys

# Logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_LEVEL = "INFO"