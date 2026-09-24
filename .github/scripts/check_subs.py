import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCES_FILE = ROOT / "sources.txt"
VALID_TXT = ROOT / "valid_subscriptions.txt"
VALID_JSON = ROOT / "valid_subscriptions.json"

DEFAULT_SOURCES = [
    "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/v2ray",
    "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/clash.yaml",
    "https://raw.githubusercontent.com/Ruk1ng001/freeSub/main/singBox.json",
    "https://raw.githubusercontent.com/a2470982985/getNode/main/v2ray.txt",
    "https://raw.githubusercontent.com/a2470982985/getNode/main/clash.yaml",
    "https://raw.githubusercontent.com/ninjastrikers/Nexus-nodes/main/configs/all.txt",
    "https://raw.githubusercontent.com/ninjastrikers/Nexus-nodes/main/configs/light.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/All_Configs_Sub.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/dongchengjie/airport/main/subs/merged/tested_within.yaml",
    "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/v.txt",
    "https://raw.githubusercontent.com/free18/v2ray/refs/heads/main/c.yaml",
    "https://raw.githubusercontent.com/SnapdragonLee/SystemProxy/master/dist/clash_config.yaml",
    "https://raw.githubusercontent.com/liketolivefree/kobabi/main/sub.txt",
    "https://raw.githubusercontent.com/pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/0xRadikal/Free-v2ray-Configs/main/verified/configs_base64.txt",
    "https://raw.githubusercontent.com/miladtahanian/multi-proxy-config-fetcher/refs/heads/main/configs/singbox_configs_all.json",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/clash.yml",
]

NODE_RE = re.compile(
    r'(?:vmess|vless|ss|ssr|trojan|hysteria|hysteria2|tuic|wireguard)://[^\s"\'<>]+',
    re.I,
)
HTML_RE = re.compile(r'<!DOCTYPE html|<html', re.I)
ERROR_RE = re.compile(r'(404|not found|invalid|expired|过期|无效|error)', re.I)


def load_sources():
    if SOURCES_FILE.exists():
        lines = SOURCES_FILE.read_text(encoding="utf-8").splitlines()
        return [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return DEFAULT_SOURCES


def fetch(session, url):
    try:
        r = session.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"
        content = r.text
        if len(content.strip()) < 10:
            return None, "empty"
        if HTML_RE.search(content[:1000]):
            return None, "html"
        if len(content) < 500 and ERROR_RE.search(content):
            return None, "error text"
        return content, None
    except Exception as e:
        return None, str(e)


def count_nodes_from_text(text):
    return len(set(NODE_RE.findall(text)))


def decode_base64_if_possible(text):
    compact = re.sub(r"\s+", "", text)
    for alt in [compact, compact.replace("-", "+").replace("_", "/")]:
        try:
            padded = alt + "=" * (-len(alt) % 4)
            decoded = base64.b64decode(padded, validate=False).decode("utf-8", errors="ignore")
            if decoded and decoded != text:
                return decoded
        except Exception:
            pass
    return None


def validate_content(url, content):
    # Clash YAML
    if url.endswith((".yaml", ".yml")) or "proxies:" in content[:2000] or "proxy-groups:" in content[:2000]:
        try:
            data = yaml.safe_load(content)
            if isinstance(data, dict):
                proxies = data.get("proxies") or data.get("Proxy") or []
                if isinstance(proxies, list) and len(proxies) > 0:
                    return True, "clash", len(proxies)
        except Exception:
            pass

    # Sing-box / JSON
    if url.endswith(".json") or content.strip().startswith(("{", "[")):
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                outbounds = data.get("outbounds") or []
                if isinstance(outbounds, list):
                    useful = [
                        o for o in outbounds
                        if isinstance(o, dict)
                        and o.get("type") not in ("direct", "block", "dns", "selector", "urltest")
                    ]
                    if len(useful) > 0:
                        return True, "sing-box", len(useful)
            if isinstance(data, list):
                return True, "json-list", len(data)
        except Exception:
            pass

    # Base64 订阅
    decoded = decode_base64_if_possible(content)
    if decoded:
        n = count_nodes_from_text(decoded)
        if n > 0:
            return True, "base64", n

    # 明文订阅
    n = count_nodes_from_text(content)
    if n > 0:
        return True, "plain", n

    return False, None, 0


def main():
    session = requests.Session()
    sources = load_sources()

    valid = []
    seen_hashes = set()
    seen_urls = set()

    for url in sources:
        if url in seen_urls:
            continue
        seen_urls.add(url)

        content, err = fetch(session, url)
        if content is None:
            print(f"[SKIP] {url} -> {err}")
            continue

        ok, fmt, count = validate_content(url, content)
        if not ok:
            print(f"[SKIP] {url} -> no valid nodes")
            continue

        h = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        if h in seen_hashes:
            print(f"[SKIP] {url} -> duplicate content")
            continue
        seen_hashes.add(h)

        valid.append({
            "url": url,
            "format": fmt,
            "node_count": count,
            "content_hash": h,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"[OK] {url} -> {fmt}, {count} nodes")

    VALID_TXT.write_text(
        "\n".join(v["url"] for v in valid) + ("\n" if valid else ""),
        encoding="utf-8",
    )
    VALID_JSON.write_text(
        json.dumps(valid, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(valid)} valid subscriptions.")


if __name__ == "__main__":
    main()
