# Taksonomi v2 — kategoriler, boyutlar, çıktı sözleşmesi

Bu dosya sistemin **tasarım kararlarını** tutar. Çalışan tanımlar
`src/config.py` içindedir ve tek doğruluk kaynağı orasıdır; buradaki metinler
o dosyayla aynı olacak şekilde güncellenir.

> **Not:** İlk sürümde 11 kategori vardı ve `personel_bilgi` de listedeydi.
> Kaldırıldı — gerekçe aşağıda "Kaldırılan kategori" bölümünde.

---

## Kategoriler (11)

Ayrım ilkesi: kategori, bildirimin hangi **bakım ekibine** gideceğini belirtir.
Arızanın nesnesi değil, sorumlusu belirleyicidir.

### 1. `mekanik_istasyon` — Mekanik ve İstasyon

**Kapsam:** Yürüyen merdiven, yürüyen yol, asansör (kabin, kapı, çağrı düğmesi,
mahsur kalma), turnikenin fiziksel/mekanik arızası (kol dönmüyor, kapak takılı,
gövde hasarlı), istasyon kayar kapıları, otomatik giriş kapıları, bariyerler.

**Hariç:** Turnikede sorun mekanik mi (kol, kapak, gövde) yoksa elektronik mi
(kart okumama, ekran, okuyucu)? Elektronikse `elektronik_sistemler`. Ekipmanın
elektriksiz kalması `elektrik_enerji`. Peron ayırıcı kapı (PAKS/PSD)
`sinyalizasyon_haberlesme` — tren hareketiyle senkron çalıştığı için.

### 2. `elektrik_enerji` — Elektrik ve Enerji

**Kapsam:** Elektrik kesintisi, elektrik çarpması ve çarpma riski, aydınlatma
armatürlerinin yanmaması, katener teli, üçüncü ray, trafo ısınması ve arızası,
jeneratör, UPS, elektrik panosu, elektrik kablosu, sigorta atması, kıvılcım ve
elektrik kaynaklı yanık kokusu.

**Hariç:** Cihazın enerjisi yerindeyken yazılımsal hata vermesi
`elektronik_sistemler`. Sinyal sisteminin kendi arızası, ray teması ve ray
voltajı sorunları `sinyalizasyon_haberlesme`.

### 3. `arac_tren` — Araç ve Tren

**Kapsam:** Sadece trenin/vagonun üzerindeki ekipman — bildirimde tren, vagon,
sefer veya makinist açıkça geçmelidir: tren kapısı arızası, araç içi
iklimlendirme (HVAC), araç içi ekran ve anons cihazı, fren ve cer sistemi,
vagon camı ve koltuğunun hasarı, tren içindeki yangın, duman ve koku.

**Hariç:** İstasyonda bulunan hiçbir ekipman girmez. Trenin gecikmesi, arıza
belirtilmeden bildirilmişse `yolcu_hizmetleri`; sinyal kaynaklı olduğu
belirtilmişse `sinyalizasyon_haberlesme`.

### 4. `sinyalizasyon_haberlesme` — Sinyalizasyon ve Haberleşme

**Kapsam:** Sinyalizasyon arızası, sinyal kaynaklı tren hareketi aksaklığı ve
sefer gecikmesi, ray üzerindeki sinyalizasyon ekipmanı, ray teması ve ray
voltajı sorunları, PAKS/PSD arızası, telsiz ve anons sisteminin teknik arızası,
acil durum anons ekipmanının fiziksel durumu, kamera (CCTV) sisteminin teknik
ve fiziksel durumu, yangın ve duman algılama sensörlerinin teknik arızası,
çevresel sensörler (hava kalitesi, nem, sıcaklık).

**Hariç:** Anonsun **içeriği** — yanlış bilgi, ses seviyesi, anonsların
karışması, anons yapılmaması — `yolcu_hizmetleri`. Ayrım net: cihaz bozuksa
burası, cihaz çalışıyor ama söylediği şey yanlışsa yolcu_hizmetleri. Kameranın
önünün afişle kapatılması (ekipman sağlam, görüş engelli) `istasyon_guvenlik`.

### 5. `elektronik_sistemler` — Elektronik Sistemler

**Kapsam:** Biletmatik, İstanbulkart yükleme ve dolum cihazı, kart okuyucu, QR
okuma hatası, para sıkışması veya iade edilmemesi, turnikenin kart okuyucusu,
turnikenin ekranı ve elektroniği, geçiş kaydının alınmaması.

**Hariç:** Turnikenin kolu dönmüyorsa, kapağı takılıysa veya gövdesi hasarlıysa
bu mekanik arızadır: `mekanik_istasyon`. Cihazın tamamen elektriksiz kalması
`elektrik_enerji`.

### 6. `yol_yapisal` — Yol ve Hat

**Kapsam:** Sadece ray hattının kendisi: ray kırılması, ray deformasyonu, makas
problemleri, travers hasarı, balast sorunu, hat üzerinde yabancı cisim veya
engel, ray bağlantı elemanları, ray ve hat drenajı.

**Hariç:** Tünelin yapısal hasarı, istasyon drenajı, su sızıntısı ve istasyon
binasına ait her yapı elemanı `altyapi_insaat`. Ray üzerindeki sinyal ekipmanı
ve ray voltajı `sinyalizasyon_haberlesme`.

### 7. `istasyon_guvenlik` — İstasyon Güvenliği

**Kapsam:** Güvenlik personelinin bulunmaması veya devriye gezmemesi, güvenlik
personelinin telsiz ve iletişim cihazının fiziksel/operasyonel sorunları,
güvenlik kamerasının görüş açısının engellenmesi, yangın söndürme ekipmanına
erişimin engellenmesi, yangın ve duman algılama (olayın kendisi), istasyonda
çıkan yangın veya yanık kokusu, seyyar satıcı ve dilenciye müdahale.

**Hariç:** Kamera, sensör ve anons cihazının **teknik** arızası
`sinyalizasyon_haberlesme` — burada ekipman değil güvenlik hizmeti söz
konusudur. Gerçekleşmiş olaylar (saldırı, kavga, hırsızlık) `guvenlik_asayis_olay`.
Temizlik ve hijyen `temizlik`.

### 8. `temizlik` — Temizlik

**Kapsam:** Temizlik yapılmaması, çöp birikmesi, çöp kovasının taşması, tuvalet
temizliği ve malzeme eksikliği, dökülen sıvı ve yiyecek lekesi, kirli zemin,
kusmuk ve idrar, sakız, kötü koku, haşere ve kemirgen, grafiti temizliği,
temizlik ekipmanı ve personeli ile ilgili operasyonel durumlar.

**Hariç:** Su sızıntısı, tavandan damlama ve yapısal kaynaklı ıslaklık
`altyapi_insaat` — kirlilik sonuçsa değil, kaynak yapısalsa oraya gider.
Yangın, duman ve yanık kokusu `istasyon_guvenlik`.

### 9. `yolcu_hizmetleri` — Yolcu Hizmetleri

**Kapsam:** Peron bilgi ekranlarındaki yanlış veya eksik bilgi, anons
içeriğinin yanlış olması, anons yapılmaması, ses seviyesinin yetersizliği,
anonsların karışması, acil durum duyurularının içeriği, hat durumu ve sefer
bilgisinin verilmemesi, sefer gecikmesi ve iptali, yönlendirme tabelalarının
eksik veya yanıltıcı olması, peron yoğunluğu, personelin yolcuya karşı
ilgisizliği.

**Hariç:** Anons ve ekran sisteminin **teknik** arızası
`sinyalizasyon_haberlesme`. Ayrım: sistem bozuksa oraya, sistem çalışıyor ama
verdiği bilgi yanlışsa buraya.

### 10. `guvenlik_asayis_olay` — Güvenlik ve Asayiş Olayı

**Kapsam:** Gerçekleşmiş olaylar: saldırı, kavga, darp, fiziksel müdahale,
taciz, hırsızlık ve yankesicilik, kayıp eşya, şüpheli şahıs, şüpheli paket,
hasta yolcu, bayılma, acil sağlık durumu, kendine zarar verme riski ve intihar
girişimi, toplu olay ve izdiham.

**Hariç:** Güvenlik personelinin bulunmaması gibi **önlem** eksiklikleri
`istasyon_guvenlik` — burası bir olayın gerçekleştiği bildirimler içindir.
Kamera ve güvenlik ekipmanının teknik arızası `sinyalizasyon_haberlesme`.

### 11. `altyapi_insaat` — Altyapı ve İnşaat

**Kapsam:** İstasyon binasının ve tünelin yapısı, binaya giren su: tünelin
yapısal hasarı, su sızıntısı, tavandan damlama, nemlenme ve rutubet, yağmur
suyunun içeri girmesi, su baskını, istasyon drenajı, gider ve mazgal
tıkanıklığı, kanalizasyon taşması, peron tavan/duvar/zemin hasarı, çatlak,
kolon, kiriş, tesisat, korkuluk, fayans dökülmesi, zeminde çukur ve çökme,
devam eden inşaat faaliyetleri, iş güvenliği riskleri.

**Hariç:** Rayın, makasın, traversin, balastın kendisi ve ray/hat drenajı
`yol_yapisal`. Yapısal sorunun sonucu oluşan kirlilik ayrı bir bildirimse
`temizlik`, ama bildirimde su/sızıntı/yapısal hasar geçiyorsa kategori her
zaman burasıdır.

---

## Kaldırılan kategori: `personel_bilgi`

İlk taslakta vardı, kaldırıldı. Gerekçe: verideki 183 kaydın tamamı gerçek İK
konusuydu (yaka kartı, bordro kesintisi, izin formu, kıyafet bedeni, mesai
ücreti) ve hiçbiri bir arıza/hizmet bildirimi değildi. Bu bir **arıza bildirim
sistemi**; personel özlük işlemleri farklı bir sistemin konusu. Kayıtlar
veriden çıkarıldı (relabel denemek anlamsızdı — başka hiçbir kategoriye
uymuyorlardı).

`intent` boyutu zaten "bilgi talebi" ve "şikayet"i yakalıyor; fark şu ki bu
intent'ler artık hep bir **arıza veya hizmet** konusu hakkında oluyor.

---

## Hariç metinleri hakkında bir tasarım kararı

İlk taslakta her kategorinin hariç listesinde "elektrik, sinyalizasyon,
haberleşme, yol, yapısal, vagon içi, yolcu bilgilendirme, temizlik/güvenlik,
personel/yönetim bunlar girmez" gibi neredeyse aynı liste vardı.

Bunlar kaldırıldı. Gerekçe: bu ifadeler LLM'e hiçbir bilgi vermiyor (zaten
örtük — bir kategori diğerlerini kapsamaz) ama prompt'u şişiriyor. 11
kategorinin her birine aynı 10 satırlık liste eklenince asıl kapsam metinleri
gürültüye gömülüyor.

Yerine sadece **gerçekten karışan sınırlar** yazıldı: hangi kavram nereye
gider ve neden. Sonuç: prompt yaklaşık %40 kısaldı, kategori F1 düşmedi.

---

## Boyutlar

Sistem üç boyutu **aynı anda** üretir. Akış:

```
KULLANICI METNİ
      ↓
   INTENT      → kullanıcının amacı (5 sınıf)
      ↓
   CATEGORY    → konu / teknik alan (11 sınıf)
      ↓
   ENTITIES    → hat, istasyon, konum, ekipman, belirti, kök sebep
      ↓
   PRIORITY    → P1–P4 (kural katmanı + model)
      ↓
   ROUTING     → ilgili birim
```

Üç sınıflandırma boyutu **tek BERTurk gövdesi** üzerinde ayrı başlıklarla
öğrenilir (multi-task). Gerekçe: bir bildirimin kategorisini belirleyen
kelimeler genellikle niyetini ve önceliğini de belirler; üç ayrı model
eğitmek bu ortak sinyali üç kez sıfırdan öğrenmek olurdu ve serviste üç taban
model bellekte tutulurdu (3 × 440 MB).

### Intent (5)

| anahtar | ad | ne zaman |
| --- | --- | --- |
| `fault_report` | Arıza Bildirimi | Bir ekipmanın çalışmaması, hasar görmesi |
| `incident_report` | Olay Bildirimi | Asayiş olayı, acil sağlık, yangın — ekipman değil **durum** |
| `information_request` | Bilgi Talebi | "Ne zaman düzelecek?", "M2 çalışıyor mu?" |
| `complaint` | Şikayet | Hizmet kalitesinden memnuniyetsizlik, somut arıza yok |
| `suggestion` | Öneri | Gelecekteki bir iyileştirme önerisi |

### Öncelik (P1–P4)

**İlk sürümde P2/P3 sınırı sayıya dayanıyordu** ("birden fazla merdiven" P2,
"tek merdiven" P3) ve model bunu öğrenemedi: P2 sınıf F1 = **0.38**.

Ölçüldü: aynı cümleler ikinci kez etiketlendiğinde iki tur arasında uyum
**%69.8** (Cohen's kappa 0.584), P2 sınıfında sadece **%38**. Yani sorun
modelde değil, **etiket tanımının belirsizliğindeydi** — model zaten
%62 ile tavana yakındı.

**Ölçüt operasyonel etkiye çevrildi ve "merdiven" mantığıyla SIRALI hale
getirildi** — her seviye net bir evet/hayır sorusu, ilk EVET'te dur:

| öncelik | ayırt edici soru | kapsam |
| --- | --- | --- |
| **P1 Kritik** | Can güvenliği tehdidi **gerçekleşmiş/gerçekleşiyor mu**? | Yangın, yoğun duman, elektrik çarpması riski, raylara kişi düşmesi, hat üzerinde nesne, tren kapısının açık seyretmesi, su baskını, acil çıkışın kapalı olması, aktif saldırı, şüpheli paket, hayati sağlık acili, intihar riski, yapısal çökme |
| **P2 Yüksek** | Sefer durdu mu / birden çok ekipman mı / yolcu fiziksel geçemiyor mu? | Sefer gecikmesi/durması/seyreltilmesi, sinyalizasyon kaynaklı aksama, PAKS arızası, yolcuların geçiş yapamaması, **"hiçbiri çalışmıyor"/"hepsi bozuk"/"bütün X'ler durdu" gibi dolaylı çoğulluk ifadeleri dahil** birden fazla ekipmanın aynı anda devre dışı kalması, ciddi su sızıntısı |
| **P3 Orta** | Arıza var ama yolculuk normal mi? | Tek bir merdiven/asansör/turnike/biletmatik arızası, birkaç lambanın yanmaması, klima çalışmaması, bir kameranın görüntü vermemesi |
| **P4 Düşük** | İşleyişi hiç etkilemiyor mu? | Kirlilik, hasarlı tabela, kozmetik hasar, bilgilendirme eksikliği, öneriler, bilgi talepleri |

**P1'de kritik bir ayrım: gerçekleşmiş tehdit ↔ varsayımsal/koşullu ifade.**
*"Yangın var", "duman doldu"* → P1. *"Yangın çıksa tüpe erişilemez", "bir şey
olursa acil çıkış kilitli"* → **P1 DEĞİL** (henüz gerçekleşmemiş bir riske
karşı önlem eksikliği bildirir), P3/P4'e düşer. Bu ayrım modelin kendi kural
katmanında da (`config.PRIORITY_RULES`) negatif lookahead ile uygulanıyor —
aksi halde "yangın tüpüne erişim yok" gibi önlem-eksikliği cümleleri de P1
kuralını yanlışlıkla tetikliyordu.

**P1 kural katmanı.** P1'i kaçırmanın bedeli asimetriktir: bir yangın
bildirimini P3 sanmak kabul edilemez, tersi sadece gereksiz aciliyet yaratır.
Bu yüzden belirli desenler modelin tahminini **ezer** ve koşulsuz P1 verir:
yangın, yoğun duman, elektrik çarpması, raylara kişi, intihar, şüpheli paket,
aktif saldırı, sağlık acili, yapısal çökme, su baskını, acil çıkış engeli.
Desenler dar ve kesin tutuldu (`config.PRIORITY_RULES`); her biri tek başına
can güvenliği tehdidi anlamına gelen ifadeler; ekipman adları (`yangın
tüpü`, `yangın merdiveni`) ve koşullu bağlaçlar (`çıksa`, `olursa`) hariç
tutuluyor.

**Bağımsız (farklı kaynaktan üretilmiş, elle etiketlenmiş) 80 kayıtlık test
setinde ölçülen ilerleme:** öncelik doğruluğu **%73.8 → %81.2**. Üç
iyileştirme birlikte etkili oldu: merdiven mantığının netleştirilmesi, P1
kural motorundaki varsayımsal-ifade hatasının düzeltilmesi, ve P2'nin
dolaylı çoğulluk ifadelerini kaçırdığı 20 hedefli örnekle giderilmesi. Etiket
tutarlılığı (kappa) bu turlar boyunca 0.584 → 0.766 → 0.721 arasında
dalgalandı — tavan hâlâ küçük örneklemin gürültüsüne tabi, ama modelin
gerçek genelleme başarısı bağımsız sette net şekilde arttı.

---

## Çıktı sözleşmesi

`POST /predict` yanıtı:

```json
{
  "intent": "fault_report",
  "intent_label": "Arıza Bildirimi",
  "intent_confidence": 0.97,

  "category": "mekanik_istasyon",
  "label": "Mekanik ve İstasyon",
  "confidence": 0.98,
  "probabilities": { "...": 0.0 },

  "line": "M4",
  "station": "Kadıköy",
  "location": "2 numaralı giriş",
  "equipment": "yürüyen merdiven",
  "symptom": "çalışmıyor",
  "root_cause": null,

  "priority": "P3",
  "priority_label": "Orta",
  "priority_rule": null,

  "evidence": ["merdiven", "yürüyen", "peron"],
  "missing_information": [],
  "possible_duplicate": false,
  "duplicate_of": null,

  "low_confidence": false,
  "manual_review": false,
  "secondary_category": null,
  "margin": 0.71,

  "routing_unit": "MEKANIK_ISTASYON",
  "log_id": 2551,
  "response_time_ms": 51.2
}
```

### Alanların kaynağı

| alan | nereden gelir |
| --- | --- |
| `intent`, `category`, `priority` | Model (üç sınıflandırma başlığı) |
| `priority_rule` | Kural katmanı — doluysa öncelik modelden değil kuraldan |
| `line`, `station`, `location`, `equipment`, `symptom`, `root_cause` | Kurallı çıkarım (`src/extract.py`) |
| `evidence` | Gradient × input (`src/evidence.py`) |
| `missing_information` | Çıkarımın boş kalan alanlarından türetilir |
| `possible_duplicate` | Veritabanı sorgusu (aynı kategori + istasyon + ekipman + son 15 dk) |
| `routing_unit` | Kategoriden eşleme (`config.ROUTING_UNIT`) |

---

## Halüsinasyon engelleyici kural

`root_cause` **sadece** bildirimde açıkça belirtilmişse doldurulur.

- *"Yürüyen merdiven çalışmıyor."* → `root_cause: null` (kullanıcı sebebi
  bilmiyor)
- *"Elektrik kesildiği için merdiven çalışmıyor."* → `root_cause: "elektrik
  kesildiği"` (kullanıcı sebebi söylüyor)
- *"Merdiven bozuk, **galiba** motoru yanmış."* → `root_cause: null`

Son örnek kritik: "galiba", "sanırım", "herhalde" gibi ifadeler kullanıcının
emin olmadığını gösterir. Sistem bunu teknik teşhis olarak kaydetmez —
kullanıcı sadece tahmin yürütüyor olabilir ve yanlış teşhis yanlış ekibe
yönlendirme demektir.

---

## `evidence` hakkında dürüst not

`evidence` alanı **gradient × input** ile üretilir: modelin tahmin ettiği
sınıfın skorunun girdi gömme vektörlerine göre türevi alınır ve gömme
değeriyle çarpılır.

Üç yöntem karşılaştırıldı:

| yöntem | ek maliyet | ne gösterir |
| --- | --- | --- |
| Sözlük eşleşmesi | ~0 ms | Hangi anahtar kelimeler var — modelin kararı **değil** |
| Integrated Gradients | ~280 ms | Gerçek model sinyali |
| **Gradient × input** (seçilen) | **~15 ms** | Gerçek model sinyali |

**Sınırı:** gradient tabanlı açıklamalar yerel doğrusal bir yaklaşıklıktır.
"Model bu token'a duyarlı" der, "model bu yüzden karar verdi" demez. Yine de
sözlük eşleşmesinden nitelik olarak farklıdır: *"tavandan su damlıyor kova
koydular"* cümlesinde sözlük "su" kelimesini bulup doğru karar verildiğini
sanırdı; gradient yöntemi modelin aslında "koydular" kelimesine takıldığını
gösterdi.
