"""
주간 인프라 사용량 점검 — Cloudflare R2 + Fly.io.

한도 초과 예상 시 Discord 경고.
"""
import json
import os
import urllib.request
from datetime import datetime, timezone

import boto3
from botocore.config import Config


# ── 임계값 ─────────────────────────────────────────────────────────────────
R2_STORAGE_WARN_GB  = 7.0   # 10GB 무료 한도 중 70% 도달 시 경고
R2_STORAGE_CRIT_GB  = 9.0   # 90% 경고
R2_WRITES_WARN      = 800_000   # 월 1,000,000 한도 중 80%
FLY_VM_WARN         = 3     # 무료 3개 한도 — 3개면 여유 없음


def check_r2() -> dict:
    account_id = os.environ.get("R2_ACCOUNT_ID", "")
    access_key = os.environ.get("R2_ACCESS_KEY", "")
    secret_key = os.environ.get("R2_SECRET_KEY", "")
    bucket     = os.environ.get("R2_BUCKET", "quant-eye-history")

    if not account_id:
        return {"ok": True, "note": "R2 credentials not set, skip"}

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )

    total_bytes = 0
    obj_count   = 0
    paginator   = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            total_bytes += obj["Size"]
            obj_count   += 1

    gb = total_bytes / 1024 ** 3
    status = "ok" if gb < R2_STORAGE_WARN_GB else "warn" if gb < R2_STORAGE_CRIT_GB else "crit"
    return {
        "status":    status,
        "gb":        round(gb, 3),
        "obj_count": obj_count,
        "limit_gb":  10,
        "pct":       round(gb / 10 * 100, 1),
    }


def check_fly() -> dict:
    token = os.environ.get("FLY_API_TOKEN", "")
    if not token:
        return {"ok": True, "note": "FLY_API_TOKEN not set, skip"}

    query = """
    {
      apps(role: null) {
        nodes {
          name
          machines {
            nodes { id state config { guest { memoryMb cpuKind cpus } } }
          }
        }
      }
    }
    """
    req = urllib.request.Request(
        "https://api.fly.io/graphql",
        data=json.dumps({"query": query}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        return {"status": "warn", "note": f"Fly.io API 오류: {e}"}

    machines = []
    for app in data.get("data", {}).get("apps", {}).get("nodes", []):
        for m in app.get("machines", {}).get("nodes", []):
            if m.get("state") in ("started", "suspended"):
                guest = m.get("config", {}).get("guest", {})
                machines.append({
                    "app":    app["name"],
                    "state":  m["state"],
                    "mem_mb": guest.get("memoryMb", 0),
                })

    running = [m for m in machines if m["state"] == "started"]
    vm_count = len(running)
    over_256 = [m for m in running if m["mem_mb"] > 256]

    status = "ok"
    if vm_count >= FLY_VM_WARN:
        status = "warn"

    return {
        "status":   status,
        "vm_count": vm_count,
        "limit":    3,
        "over_256": over_256,
        "machines": running,
    }


def send_discord(webhook: str, msg: str) -> None:
    if not webhook:
        print(f"[DISCORD 미설정] {msg}")
        return
    payload = json.dumps({"content": msg}).encode()
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Discord 전송 실패: {e}")


def main() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    webhook = os.environ.get("DISCORD_WEBHOOK", "")

    lines = [f"**📊 인프라 사용량 리포트** ({now})"]
    alerts = []

    # R2 점검
    r2 = check_r2()
    if "note" in r2:
        lines.append(f"☁️ **R2**: {r2['note']}")
    else:
        icon = "✅" if r2["status"] == "ok" else ("⚠️" if r2["status"] == "warn" else "🚨")
        lines.append(
            f"{icon} **R2 스토리지**: {r2['gb']} GB / 10 GB ({r2['pct']}%)"
            f"  |  객체 {r2['obj_count']}개"
        )
        if r2["status"] == "warn":
            alerts.append(f"⚠️ R2 스토리지 {r2['pct']}% 사용 중 — 아카이브 정리 필요")
        elif r2["status"] == "crit":
            alerts.append(f"🚨 R2 스토리지 {r2['pct']}% — 즉시 조치 필요!")

    # Fly.io 점검
    fly = check_fly()
    if "note" in fly:
        lines.append(f"🚀 **Fly.io**: {fly['note']}")
    else:
        icon = "✅" if fly["status"] == "ok" else "⚠️"
        lines.append(f"{icon} **Fly.io VM**: {fly['vm_count']}개 실행 중 / 무료 한도 3개")
        for m in fly.get("machines", []):
            mem_icon = "🔴" if m["mem_mb"] > 256 else "🟢"
            lines.append(f"   {mem_icon} `{m['app']}` — {m['mem_mb']}MB ({m['state']})")
        if fly.get("over_256"):
            alerts.append(
                f"⚠️ 256MB 초과 VM {len(fly['over_256'])}개 실행 중 → 무료 한도 초과 가능"
            )
        if fly["vm_count"] >= 3:
            alerts.append("⚠️ Fly.io VM 3개 한도 도달 — 새 앱 배포 시 비용 발생")

    print("\n".join(lines))

    if alerts:
        alert_msg = "\n".join(lines) + "\n\n**🔔 알림:**\n" + "\n".join(alerts)
        send_discord(webhook, alert_msg)
    else:
        # 정상이어도 주간 요약은 Discord에 전송
        send_discord(webhook, "\n".join(lines))


if __name__ == "__main__":
    main()
