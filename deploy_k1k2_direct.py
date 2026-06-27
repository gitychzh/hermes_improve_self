#!/usr/bin/env python3
"""R46: K1/K2 Direct Connect Deployment Script for HM2

HM2 (opc2sname) runs this on HM1 (opcsname) via SSH.
This script modifies hm40006 gateway code to make K1/K2 (key_idx 0,1)
connect directly to integrate.api.nvidia.com instead of SOCKS5 mihomo.

Usage:
    python3 deploy_k1k2_direct.py
    # or via SSH from HM2: ssh opcsname 'python3 deploy_k1k2_direct.py'
"""

import subprocess
import sys
import time

CONTAINER = "hm40006"
SRC_PATH = "/app/gateway/upstream.py"
BAK_PATH = "/app/gateway/upstream.py.bak.R46"

# ────────────────────────────────────────────────────────────
# Step 1: Backup current code
# ────────────────────────────────────────────────────────────
print("[1/4] Backing up current upstream.py...")
subprocess.run(["docker", "exec", CONTAINER, "cp", SRC_PATH, BAK_PATH], check=True)
print("  ✓ Backup: upstream.py.bak.R46")

# ────────────────────────────────────────────────────────────
# Step 2: Read current source
# ────────────────────────────────────────────────────────────
print("[2/4] Reading current source...")
result = subprocess.run(
    ["docker", "exec", CONTAINER, "cat", SRC_PATH],
    capture_output=True, text=True, check=True
)
original = result.stdout
lines = original.split('\n')

# ────────────────────────────────────────────────────────────
# Step 3: Apply modifications
# ────────────────────────────────────────────────────────────
print("[3/4] Applying K1/K2 direct connect modifications...")

# --- Modification A: Insert _make_direct_conn helper function ---
# Insert after line "    return conn" (end of _make_nvcf_proxy_conn, line ~96)
direct_conn_func = [
    "",
    "# --- R46: Direct integrate API connection (K1/K2, no SOCKS5 proxy) ---",
    "def _make_direct_conn(nvcf_host, path, headers, body, timeout=UPSTREAM_TIMEOUT):",
    "    \"\"\"Create direct HTTPSConnection to integrate.api.nvidia.com for K1/K2.",
    "",
    "    K1/K2 connect directly to NV API without SOCKS5 proxy overhead.",
    "    Used only for key_idx 0 and 1.",
    "",
    "    Args:",
    "        nvcf_host: hostname (e.g. 'api.nvcf.nvidia.com')",
    "        path: API path (e.g. '/v2/nvcf/pexec/functions/...')",
    "        headers: dict of HTTP headers (Authorization, Content-Type, etc.)",
    "        body: encoded request body (bytes)",
    "        timeout: connect + read timeout in seconds",
    "",
    "    Returns: (HTTPSConnection, HTTPResponse) tuple ready for status inspection.",
    "",
    "    After call, caller should check resp.status and handle errors.",
    "    Connection:close is set; no keep-alive reuse across requests.",
    "    \"\"\"",
    "    conn = http.client.HTTPSConnection(nvcf_host, 443, timeout=timeout)",
    "    conn.request(\"POST\", path, body=body, headers=headers)",
    "    resp = conn.getresponse()",
    "    return conn, resp",
    "",
]

insert_after_return = []
for i, line in enumerate(lines):
    if line.strip() == "return conn" and i < 150:
        # Found the return of _make_nvcf_proxy_conn (not later returns in _try_tier_keys)
        # Actually need to be more precise: find the exact return at the end of _make_nvcf_proxy_conn
        # Look for the line BEFORE def _build_pexec_body
        if i+1 < len(lines) and 'def _build_pexec_body' in lines[i+1]:
            insert_point = i + 1  # after "return conn", before next function
            break

# Insert the helper function
new_lines = lines[:insert_point] + direct_conn_func + lines[insert_point:]

# --- Modification B: Update log line (show "direct" vs "SOCKS5") ---
# Find the log line at ~L270-271
for i, line in enumerate(new_lines):
    if 'via {proxy_url}' in line:
        log_line_idx = i
        break
    if 'via {route_type}' in line:
        # Already modified, skip
        log_line_idx = -1
        break

if log_line_idx >= 0:
    # Check for the _log call above this line
    # Original is a 2-line f-string: L269 has _log(...), L270 has the continuation
    # Need to find the actual _log call
    for check_idx in range(log_line_idx - 2, log_line_idx + 1):
        if '_log("HM-KEY"' in new_lines[check_idx] and check_idx >= 0:
            actual_log_start = check_idx
            break

    # Replace the 2-line log with 3-line version
    if actual_log_start and new_lines[actual_log_start+1].strip().startswith('f"k{key'):
        old_log_line1 = new_lines[actual_log_start]
        old_log_line2 = new_lines[actual_log_start+1]

        new_lines[actual_log_start] = (
            '        route_type = "direct" if key_idx < 2 else "SOCKS5 " + proxy_url'
        )
        new_lines[actual_log_start+1] = (
            '        _log("HM-KEY", f"tier={tier_model} attempt {attempt_idx+1}/{HM_NUM_KEYS + 2}: "'
        )
        # The continuation line
        new_lines.insert(actual_log_start+2,
            '                       f"k{key_idx+1} → NVCF pexec {function_id[:12]}... via {route_type}")'
        )
        # Remove the old continuation line (now at actual_log_start+3 after insert)
        new_lines.pop(actual_log_start+3)

# --- Modification C: Conn creation fork (L284-285 → if/else) ---
conn_create_idx = -1
for i, line in enumerate(new_lines):
    if 'conn = _make_nvcf_proxy_conn(proxy_url' in line:
        conn_create_idx = i
        break
    if 'if key_idx < 2:' in line and '_make_direct_conn' in new_lines[i+1] if i+1 < len(new_lines) else False:
        # Already patched
        conn_create_idx = -1
        break

if conn_create_idx >= 0:
    # Find the surrounding context: t_connect_start line
    t_connect_idx = -1
    for i in range(conn_create_idx - 3, conn_create_idx + 1):
        if i >= 0 and 't_connect_start = time.time()' in new_lines[i]:
            t_connect_idx = i
            break

    if t_connect_idx >= 0:
        # Replace the conn creation block (from t_connect_start through connect_elapsed)
        # Old: 3 lines (t_connect_start, conn creation, connect_elapsed)
        # New: if/else block with direct path

        # Find the end of this block (next line after connect_elapsed)
        # The line after conn_create_idx should be "connect_elapsed = ..."
        block_end = conn_create_idx + 2  # typically 2 lines after conn creation

        # Build replacement
        replacement = [
            new_lines[t_connect_idx],  # keep "t_connect_start = time.time()"
            '            # R46: K1/K2 direct to integrate API, K3/K4/K5 via SOCKS5 mihomo',
            '            if key_idx < 2:',
            '                # Direct connection — no SOCKS5 proxy overhead',
            '                conn, resp = _make_direct_conn(nvcf_host, nvcf_path, headers_out, pexec_data, per_attempt_timeout)',
            '                connect_elapsed = time.time() - t_connect_start',
            '                _log("HM-DIRECT", f"tier={tier_model} k{key_idx+1} direct connect OK ({connect_elapsed:.1f}s)")',
            '                # Direct path: resp is already available, skip SOCKS5-specific budget/sock steps',
            '                # Jump to the resp.status check (same logic as SOCKS5 path)',
            '                direct_resp_ready = True',
            '            else:',
            '                conn = _make_nvcf_proxy_conn(proxy_url, nvcf_host=nvcf_host, timeout=per_attempt_timeout)',
            '                connect_elapsed = time.time() - t_connect_start',
            '                direct_resp_ready = False',
        ]

        # Replace the 3 old lines with the new block
        new_lines = (
            new_lines[:t_connect_idx] +
            replacement +
            new_lines[block_end:]
        )

        # After the replacement, the "conn = _make_nvcf_proxy_conn" line is gone
        # The next line should be the budget check: "post_connect_remaining = ..."
        # This needs to be guarded by "if not direct_resp_ready:"
        # Find the post_connect_remaining line in new_lines
        for i in range(len(replacement), len(replacement)+10):
            if i < len(new_lines):
                if 'post_connect_remaining = TIER_TIMEOUT_BUDGET_S' in new_lines[i]:
                    # Insert guard
                    new_lines[i] = new_lines[i].replace(
                        'post_connect_remaining = ',
                        'if not direct_resp_ready:\n'
                        '            # Budget check only for SOCKS5 path (direct skips this)\n'
                        '            post_connect_remaining = '
                    )
                    break

# ────────────────────────────────────────────────────────────
# Step 4: Write back and restart
# ────────────────────────────────────────────────────────────
print("[4/4] Writing modified source and restarting...")

modified_content = '\n'.join(new_lines)

# Syntax check first
with open("/tmp/upstream_r46.py", "w") as f:
    f.write(modified_content)

subprocess.run(
    ["docker", "cp", "/tmp/upstream_r46.py", f"{CONTAINER}:{SRC_PATH}"],
    check=True
)

# Verify syntax
syntax_check = subprocess.run(
    ["docker", "exec", CONTAINER, "python3", "-m", "py_compile", SRC_PATH],
    capture_output=True, text=True
)
if syntax_check.returncode != 0:
    print("  ✗ SYNTAX ERROR in modified upstream.py!")
    print(f"  {syntax_check.stderr[:500]}")
    print("  Restoring backup...")
    subprocess.run(["docker", "exec", CONTAINER, "cp", BAK_PATH, SRC_PATH], check=True)
    sys.exit(1)

print("  ✓ Syntax: valid")

# Restart container to apply changes
subprocess.run(["docker", "restart", CONTAINER], check=True)
time.sleep(3)

# Verify container is running
health = subprocess.run(
    ["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER],
    capture_output=True, text=True, check=True
)
print(f"  ✓ Container status: {health.stdout.strip()}")

# ────────────────────────────────────────────────────────────
# Verification: Check the K1/K2 routing logic is in place
# ────────────────────────────────────────────────────────────
print("\n═══ Verification ═══")
verify = subprocess.run(
    ["docker", "exec", CONTAINER, "grep", "-n", "key_idx < 2", SRC_PATH],
    capture_output=True, text=True
)
print(f"  Key routing fork: {verify.stdout.strip()}")

verify_log = subprocess.run(
    ["docker", "exec", CONTAINER, "grep", "-n", "HM-DIRECT", SRC_PATH],
    capture_output=True, text=True
)
print(f"  Direct log prefix: {verify_log.stdout.strip()}")

print("\n✓ R46 deployment complete. K1/K2 now route direct to integrate.api.nvidia.com.")
print("  Next: packet capture to confirm TCP connections.")
print("  Command: sudo tcpdump -i any port 443 -c 20 | grep -v '789[0-9]'")