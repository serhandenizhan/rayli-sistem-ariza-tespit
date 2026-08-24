"""
OpenRouter'da su an gercekten neyin ucretsiz oldugunu ve Claude modellerinin
fiyatini gosterir. Tahmin etmek yerine canli API'den sorgular.

Kullanim:
    python -m src.check_openrouter_models
"""

import requests


def main() -> None:
    resp = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
    resp.raise_for_status()
    models = resp.json()["data"]

    free = [
        m for m in models
        if m["id"].endswith(":free")
    ]
    claude = [
        m for m in models
        if "anthropic" in m["id"].lower() or "claude" in m["id"].lower()
    ]

    print(f"\n=== UCRETSIZ MODELLER ({len(free)} adet) ===")
    print(f"{'model id':<45} {'context':>10}")
    for m in sorted(free, key=lambda x: x["id"]):
        ctx = m.get("context_length", "?")
        print(f"{m['id']:<45} {ctx!s:>10}")

    print(f"\n=== CLAUDE MODELLERI ({len(claude)} adet, OpenRouter uzerinden UCRETLI) ===")
    print(f"{'model id':<40} {'input $/1M':>12} {'output $/1M':>12} {'context':>10}")
    for m in sorted(claude, key=lambda x: x["id"]):
        pricing = m.get("pricing", {})
        try:
            inp = float(pricing.get("prompt", 0)) * 1_000_000
            out = float(pricing.get("completion", 0)) * 1_000_000
        except (TypeError, ValueError):
            inp = out = 0
        ctx = m.get("context_length", "?")
        print(f"{m['id']:<40} {inp:>11.2f} {out:>12.2f} {ctx!s:>10}")

    print(
        "\nNOT: Claude modelleri burada ucretsiz DEGIL — OpenRouter kredi "
        "bakiyenden dusuluyor, minimum yukleme $5 + %5.5 platform ucreti. "
        "Claude'a gececeksen dogrudan console.anthropic.com daha ucuz."
    )


if __name__ == "__main__":
    main()
