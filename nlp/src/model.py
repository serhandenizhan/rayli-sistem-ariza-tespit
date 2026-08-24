"""
Cok basli (multi-task) siniflandirma modeli: tek BERTurk govdesi, uc cikti.

NEDEN TEK GOVDE, UC BASLIK: bir bildirimin kategorisi, niyeti ve onceligi ayni
cumleden okunur ve birbirleriyle iliskilidir -- "peronda kavga var" cumlesinde
kategoriyi belirleyen kelimeler ayni zamanda intent'i (incident_report) ve
onceligi (P1) de belirler. Uc ayri model egitmek bu ortak sinyali uc kez
sifirdan ogrenmek olurdu; ustelik serviste uc taban model bellekte tutulurdu
(3 x 440 MB). Ortak govde + uc kucuk baslik hem bu paylasimi saglar hem de
bellekte tek model tutar.

KAYIP TOPLAMI: uc gorevin kaybi toplanir. Agirliklandirma YAPILMADI cunku uc
gorev de ayni olcekte (capraz entropi, benzer sinif sayilari) ve agirlik
eklemek ayarlanacak yeni bir hiperparametre demek olurdu. Kategori 11 sinif,
intent 5, oncelik 4 -- yakin buyuklukler.

LoRA burada govdeye uygulanir (TaskType.FEATURE_EXTRACTION); baslıklar zaten
kucuk ve sifirdan egitildikleri icin tamamen egitilebilir birakilir.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn
from transformers import AutoConfig, AutoModel

from src import config as C

BASLIK_DOSYA = "basliklar.pt"
GOVDE_DIZIN = "govde"

# (alan adi, sinif sayisi) -- yeni bir boyut eklenecekse tek yer burasi.
GOREVLER = (
    ("kategori", C.NUM_LABELS),
    ("intent", C.NUM_INTENTS),
    ("oncelik", C.NUM_PRIORITIES),
)


class CokBaslikliSiniflandirici(nn.Module):
    """BERTurk govdesi + gorev basina bir dogrusal siniflandirma katmani."""

    def __init__(self, taban_model: str = C.BASE_MODEL, lora: bool = True):
        super().__init__()
        self.taban_model = taban_model
        self.lora_aktif = lora

        govde = AutoModel.from_pretrained(taban_model)
        if lora:
            from peft import LoraConfig, TaskType, get_peft_model
            govde = get_peft_model(govde, LoraConfig(
                task_type=TaskType.FEATURE_EXTRACTION,
                r=C.LORA_R,
                lora_alpha=C.LORA_ALPHA,
                lora_dropout=C.LORA_DROPOUT,
                target_modules=C.LORA_TARGET_MODULES,
            ))
        self.govde = govde

        gizli = AutoConfig.from_pretrained(taban_model).hidden_size
        self.dropout = nn.Dropout(C.LORA_DROPOUT)
        self.basliklar = nn.ModuleDict({
            ad: nn.Linear(gizli, n) for ad, n in GOREVLER
        })

    def temsil(self, input_ids, attention_mask) -> torch.Tensor:
        """[CLS] token temsili.

        BERT'in kendi pooler'i yerine dogrudan [CLS] gizli durumu kullaniliyor:
        pooler tanh'li ek bir katman ve siniflandirmada olcumlu bir faydasi
        gorulmedi; ayrica LoRA sarmalamasi altinda her zaman doniyor olmasi
        garanti degil.
        """
        cikti = self.govde(input_ids=input_ids, attention_mask=attention_mask)
        return cikti.last_hidden_state[:, 0]

    def forward(self, input_ids, attention_mask, **etiketler):
        havuz = self.dropout(self.temsil(input_ids, attention_mask))
        logitler = {ad: self.basliklar[ad](havuz) for ad, _ in GOREVLER}

        kayip = None
        if any(etiketler.get(ad) is not None for ad, _ in GOREVLER):
            kayip_fn = nn.CrossEntropyLoss()
            kayip = sum(
                kayip_fn(logitler[ad], etiketler[ad])
                for ad, _ in GOREVLER if etiketler.get(ad) is not None
            )
        return {"loss": kayip, "logits": logitler}

    # -- kayit / yukleme ---------------------------------------------------
    #
    # save_pretrained kullanilamiyor (bu bir HF modeli degil), o yuzden govde
    # ile basliklar ayri kaydediliyor: govde PEFT'in kendi formatinda (LoRA
    # adaptoru ~2.4 MB), basliklar duz bir state_dict olarak.

    def kaydet(self, dizin: Path) -> None:
        dizin = Path(dizin)
        dizin.mkdir(parents=True, exist_ok=True)
        self.govde.save_pretrained(dizin / GOVDE_DIZIN)
        torch.save(self.basliklar.state_dict(), dizin / BASLIK_DOSYA)
        (dizin / "model_yapisi.json").write_text(json.dumps({
            "taban_model": self.taban_model,
            "lora": self.lora_aktif,
            "gorevler": {ad: n for ad, n in GOREVLER},
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def yukle(cls, dizin: Path) -> "CokBaslikliSiniflandirici":
        dizin = Path(dizin)
        yapi = json.loads((dizin / "model_yapisi.json").read_text(encoding="utf-8"))
        model = cls(yapi["taban_model"], lora=False)   # LoRA'yi asagida takiyoruz

        if yapi["lora"]:
            from peft import PeftModel
            model.govde = PeftModel.from_pretrained(model.govde, dizin / GOVDE_DIZIN)
            model.lora_aktif = True
        else:
            from transformers import AutoModel as _AM
            model.govde = _AM.from_pretrained(dizin / GOVDE_DIZIN)

        model.basliklar.load_state_dict(
            torch.load(dizin / BASLIK_DOSYA, map_location="cpu")
        )
        return model


def tahmin_dagilimlari(model, tokenizer, metinler: list[str], cihaz,
                       parti_boyu: int = C.BATCH_SIZE) -> dict[str, torch.Tensor]:
    """Her gorev icin (N, sinif) olasilik matrisi doner."""
    model.eval()
    birikim: dict[str, list[torch.Tensor]] = {ad: [] for ad, _ in GOREVLER}
    with torch.no_grad():
        for i in range(0, len(metinler), parti_boyu):
            enc = tokenizer(
                metinler[i:i + parti_boyu],
                truncation=True, padding="max_length",
                max_length=C.MAX_LENGTH, return_tensors="pt",
            ).to(cihaz)
            cikti = model(**enc)
            for ad, _ in GOREVLER:
                birikim[ad].append(torch.softmax(cikti["logits"][ad], dim=-1).cpu())
    return {ad: torch.cat(p) for ad, p in birikim.items()}
