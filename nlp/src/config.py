"""
Metro Istanbul Ariza Tespit Siniflandirici -- merkezi konfigurasyon.

Bu dosya projenin TEK dogruluk kaynagidir. Kategori taksonomisi, yollar,
hiperparametreler ve threshold degeri sadece burada tanimlanir; diger tum
moduller (generate_seed, generate_data, preprocess, train, evaluate, backend)
buradan import eder.

NOT: Bu dosyadaki Turkce metinler (kategori aciklamalari, kurallar, istasyon
adlari) dogru aksanlarla yazilir -- bunlar LLM prompt'larina birebir enjekte
ediliyor, ASCII yazim modele yanlis stil sinyali verir. Python UTF-8 kaynak
dosyalarinda Turkce karakterlerin hicbir teknik sakincasi yoktur; ASCII
kisitlamasi sadece ReportLab PDF font render sorunuyla ilgiliydi, kaynak
koda genellenmemeliydi.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Yollar
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
SEED_DIR = DATA_DIR / "seed"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = ROOT_DIR / "model"

SEED_FILE = SEED_DIR / "seed.jsonl"        # few-shot yemi olarak kullanilir
GOLD_FILE = SEED_DIR / "gold.jsonl"        # few-shot'ta ASLA kullanilmaz, saf test
# v1 taksonomisine aitti (bkz. CLAUDE.md Acik Nokta #4), Taksonomi v2'de
# devre disi -- artik var olmadigi icin GOLD_FILE'a bagli her sey (ornekler
# ucnoktasi, preprocess sizinti kontrolu) sessizce bos/atlanmis durumda.
# EXAMPLES_FILE ayri tutuluyor cunku kullanicinin bagimsiz test seti
# (yeni_gold_deneme.jsonl) GOLD_FILE'a atanirsa generate_seed.py/
# apply_review.py bir sonraki calistirmada onun UZERINE yazabilir --
# egitimde hic kullanilmamis bagimsiz bir seti riske atmamak icin
# /examples ucnoktasi kendi ayri sabitini kullaniyor.
EXAMPLES_FILE = SEED_DIR / "yeni_gold_deneme.jsonl"
RAW_FILE = RAW_DIR / "amplified.jsonl"     # Ollama ciktisi (ham)
CLEAN_FILE = PROCESSED_DIR / "clean.csv"   # temizlenmis + dedup

TRAIN_FILE = PROCESSED_DIR / "train.csv"
VAL_FILE = PROCESSED_DIR / "val.csv"
TEST_FILE = PROCESSED_DIR / "test.csv"
GOLD_TEST_FILE = PROCESSED_DIR / "gold_test.csv"

for _d in (SEED_DIR, RAW_DIR, PROCESSED_DIR, MODEL_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Kategori taksonomisi
#
# Ayrim ilkesi: kategori, bildirimin hangi BAKIM EKIBINE yonlendirilecegini
# belirtir. Arizanin nesnesi degil, sorumlusu belirleyicidir.
# ---------------------------------------------------------------------------

# HARIC METINLERI HAKKINDA: burada "diger tum kategoriler girmez" gibi genel
# ifadeler BILEREK yok. Onlar LLM'e hicbir bilgi vermiyor (zaten ortuk) ama
# prompt'u sisiriyor -- 11 kategorinin her birine 10 satirlik ayni liste
# eklenince kapsam metinleri gurultuye gomuluyor. Bunun yerine sadece
# GERCEKTEN KARISAN sinirlar yaziliyor: hangi kavram nereye gider ve neden.
# Olcum: sadelestirilmis metinlerle prompt ~%40 kisaldi ve kategori F1 dusmedi.

CATEGORIES = {
    "mekanik_istasyon": {
        "display": "Mekanik ve İstasyon",
        "color": "#0891b2",
        "scope": (
            "İstasyondaki hareketli MEKANİK ekipman: yürüyen merdiven, "
            "yürüyen yol, asansör (kabin, kapı, çağrı düğmesi, mahsur kalma), "
            "turnikenin fiziksel/mekanik arızası (kol dönmüyor, kapak takılı, "
            "gövde hasarlı), istasyon kayar kapıları, otomatik giriş kapıları, "
            "bariyerler"
        ),
        "exclude": (
            "Turnikede sorun MEKANİK mi (kol, kapak, gövde) yoksa ELEKTRONİK mi "
            "(kart okumama, ekran, okuyucu)? Elektronikse 'elektronik_sistemler'. "
            "Ekipmanın elektriksiz kalması veya sigorta atması 'elektrik_enerji'. "
            "Peron ayırıcı kapı (PAKS/PSD) 'sinyalizasyon_haberlesme' -- tren "
            "hareketiyle senkron çalıştığı için."
        ),
    },
    "elektrik_enerji": {
        "display": "Elektrik ve Enerji",
        "color": "#f59e0b",
        "scope": (
            "Enerji besleme ve aydınlatma: elektrik kesintisi, elektrik "
            "çarpması ve çarpma riski, aydınlatma armatürlerinin yanmaması, "
            "katener teli, üçüncü ray, trafo ısınması ve arızası, jeneratör, "
            "UPS, elektrik panosu, elektrik kablosu, sigorta atması, kıvılcım "
            "ve elektrik kaynaklı yanık kokusu"
        ),
        "exclude": (
            "Cihazın enerjisi yerindeyken yazılımsal hata vermesi "
            "'elektronik_sistemler'. Sinyal sisteminin kendi arızası, ray "
            "teması ve ray voltajı sorunları 'sinyalizasyon_haberlesme'."
        ),
    },
    "arac_tren": {
        "display": "Araç ve Tren",
        "color": "#2563eb",
        "scope": (
            "SADECE trenin/vagonun üzerindeki ekipman -- bildirimde tren, "
            "vagon, sefer veya makinist açıkça geçmelidir: tren kapısı arızası, "
            "araç içi iklimlendirme (HVAC, vagon çok sıcak veya soğuk), araç "
            "içi ekran ve anons cihazı, fren ve cer sistemi, vagon camı ve "
            "koltuğunun hasarı, tren içindeki yangın, duman ve koku"
        ),
        "exclude": (
            "İSTASYONDA bulunan hiçbir ekipman buraya girmez -- peron kapısı, "
            "yürüyen merdiven, asansör, turnike, istasyon aydınlatması kendi "
            "kategorilerine gider. Trenin gecikmesi, arıza belirtilmeden "
            "bildirilmişse 'yolcu_hizmetleri'; sinyal kaynaklı olduğu "
            "belirtilmişse 'sinyalizasyon_haberlesme'."
        ),
    },
    "sinyalizasyon_haberlesme": {
        "display": "Sinyalizasyon ve Haberleşme",
        "color": "#6366f1",
        "scope": (
            "Sinyal, tren kontrolü ve haberleşme DONANIMI: sinyalizasyon "
            "arızası, sinyal kaynaklı tren hareketi aksaklığı ve sefer "
            "gecikmesi, ray üzerindeki sinyalizasyon ekipmanı, ray teması ve "
            "ray voltajı sorunları, peron ayırıcı kapı (PAKS/PSD) arızası, "
            "telsiz ve anons sisteminin teknik arızası, acil durum anons "
            "ekipmanının fiziksel durumu, kamera (CCTV) sisteminin teknik ve "
            "fiziksel durumu, yangın ve duman algılama sensörlerinin teknik "
            "arızası, çevresel sensörler (hava kalitesi, nem, sıcaklık)"
        ),
        "exclude": (
            "Anonsun İÇERİĞİ -- yanlış bilgi, ses seviyesi, anonsların "
            "karışması, anons yapılmaması -- 'yolcu_hizmetleri'. Ayrım net: "
            "cihaz BOZUKSA burası, cihaz çalışıyor ama SÖYLEDİĞİ ŞEY "
            "yanlış/eksikse yolcu_hizmetleri. "
            "DİKKAT -- metinde 'cihaz' veya 'sistem' kelimesi geçmesi TEK "
            "BAŞINA bu kategoriyi göstermez: 'cihazın SESİ KISIK/DÜŞÜK' ve "
            "'anons/duyuru YAPILMADI/yapılmıyor' ifadeleri her zaman "
            "'yolcu_hizmetleri'ne gider, cihaz kelimesi geçse bile -- "
            "buradaki 'cihaz arızası' SADECE cihazın hiç ses ÜRETEMEMESİ, "
            "hiç ÇALIŞMAMASI, tamamen BOZUK/SUSMUŞ olmasıdır. "
            "Kameranın önünün afiş veya eşyayla kapatılması (ekipman "
            "sağlam, görüş engelli) 'istasyon_guvenlik'."
        ),
    },
    "elektronik_sistemler": {
        "display": "Elektronik Sistemler",
        "color": "#7c3aed",
        "scope": (
            "Biletleme ve ödeme elektroniği: biletmatik, İstanbulkart yükleme "
            "ve dolum cihazı, kart okuyucu, QR okuma hatası, para sıkışması "
            "veya iade edilmemesi, turnikenin kart okuyucusu, turnikenin "
            "ekranı ve elektroniği, geçiş kaydının alınmaması"
        ),
        "exclude": (
            "Turnikenin kolu dönmüyorsa, kapağı takılıysa veya gövdesi "
            "hasarlıysa bu mekanik arızadır: 'mekanik_istasyon'. Cihazın "
            "tamamen elektriksiz kalması 'elektrik_enerji'."
        ),
    },
    "yol_yapisal": {
        "display": "Yol ve Hat",
        "color": "#a16207",
        "scope": (
            "SADECE ray hattının kendisi: ray kırılması, ray deformasyonu, "
            "makas problemleri, travers hasarı, balast sorunu, hat üzerinde "
            "yabancı cisim veya engel, ray bağlantı elemanları, ray ve hat "
            "drenajı"
        ),
        "exclude": (
            "Tünelin yapısal hasarı, istasyon drenajı, su sızıntısı ve istasyon "
            "binasına ait her yapı elemanı 'altyapi_insaat' -- burası sadece "
            "rayın ve hattın kendisiyle ilgilidir. Ray üzerindeki sinyal "
            "ekipmanı ve ray voltajı 'sinyalizasyon_haberlesme'."
        ),
    },
    "istasyon_guvenlik": {
        "display": "İstasyon Güvenliği",
        "color": "#ea580c",
        "scope": (
            "İstasyonun güvenlik OPERASYONU ve önlem durumu: güvenlik "
            "personelinin bulunmaması veya devriye gezmemesi, güvenlik "
            "personelinin telsiz ve iletişim cihazının fiziksel/operasyonel "
            "sorunları, güvenlik kamerasının görüş açısının engellenmesi, "
            "yangın söndürme ekipmanına erişimin engellenmesi, yangın ve duman "
            "algılama (olayın kendisi), istasyonda çıkan yangın veya yanık "
            "kokusu, seyyar satıcı ve dilenciye müdahale"
        ),
        "exclude": (
            "Kamera, sensör ve anons cihazının TEKNİK arızası "
            "'sinyalizasyon_haberlesme' -- burada ekipman değil güvenlik "
            "HİZMETİ söz konusudur. Saldırı, kavga, taciz, hırsızlık, kayıp "
            "eşya, hasta yolcu gibi gerçekleşmiş olaylar "
            "'guvenlik_asayis_olay'. Temizlik ve hijyen 'temizlik'."
        ),
    },
    "temizlik": {
        "display": "Temizlik",
        "color": "#65a30d",
        "scope": (
            "Temizlik ve hijyen: temizlik yapılmaması, çöp birikmesi, çöp "
            "kovasının taşması, tuvalet temizliği ve malzeme eksikliği, "
            "dökülen sıvı ve yiyecek lekesi, kirli zemin, kusmuk ve idrar, "
            "sakız, kötü koku, haşere ve kemirgen, grafiti temizliği, temizlik "
            "ekipmanı ve personeli ile ilgili operasyonel durumlar"
        ),
        "exclude": (
            "Su sızıntısı, tavandan damlama ve yapısal kaynaklı ıslaklık "
            "'altyapi_insaat' -- kirlilik SONUÇSA değil KAYNAK yapısalsa oraya "
            "gider. Yangın, duman ve yanık kokusu 'istasyon_guvenlik'. "
            "Güvenlik personeli ve ekipmanı 'istasyon_guvenlik'."
        ),
    },
    "yolcu_hizmetleri": {
        "display": "Yolcu Hizmetleri",
        "color": "#059669",
        "scope": (
            "Yolcuya verilen BİLGİNİN kendisi ve sefer hizmeti: peron bilgi "
            "ekranlarındaki yanlış veya eksik bilgi, anons içeriğinin yanlış "
            "olması, anons yapılmaması, ses seviyesinin yetersizliği, "
            "anonsların karışması, acil durum duyurularının içeriği, hat "
            "durumu ve sefer bilgisinin verilmemesi, sefer gecikmesi ve "
            "iptali, yönlendirme tabelalarının eksik veya yanıltıcı olması, "
            "peron yoğunluğu, personelin yolcuya karşı ilgisizliği"
        ),
        "exclude": (
            "Anons ve ekran sisteminin TEKNİK arızası (cihaz hiç ses "
            "üretmiyor, tamamen susmuş, ekran hiç açılmıyor) "
            "'sinyalizasyon_haberlesme'. Ayrım: sistem bozuksa oraya, sistem "
            "çalışıyor ama verdiği bilgi yanlış, eksik veya SESİ KISIKSA "
            "buraya -- 'cihaz' kelimesinin metinde geçmesi kategoriyi "
            "sinyalizasyon_haberlesme yapmaz."
        ),
    },
    "guvenlik_asayis_olay": {
        "display": "Güvenlik ve Asayiş Olayı",
        "color": "#dc2626",
        "scope": (
            "GERÇEKLEŞMİŞ asayiş ve acil sağlık olayları: saldırı, kavga, "
            "darp, fiziksel müdahale, taciz, hırsızlık ve yankesicilik, kayıp "
            "eşya, şüpheli şahıs, şüpheli paket, hasta yolcu, bayılma, acil "
            "sağlık durumu, kendine zarar verme riski ve intihar girişimi, "
            "toplu olay ve izdiham"
        ),
        "exclude": (
            "Güvenlik personelinin bulunmaması, devriye gezmemesi gibi ÖNLEM "
            "eksiklikleri 'istasyon_guvenlik' -- burası bir OLAYIN "
            "gerçekleştiği bildirimler içindir. Kamera ve güvenlik ekipmanının "
            "teknik arızası 'sinyalizasyon_haberlesme'."
        ),
    },
    "altyapi_insaat": {
        "display": "Altyapı ve İnşaat",
        "color": "#78716c",
        "scope": (
            "İstasyon BİNASININ ve tünelin yapısı, ve binaya giren su: tünelin "
            "yapısal hasarı, su sızıntısı, tavandan damlama, nemlenme ve "
            "rutubet, yağmur suyunun içeri girmesi, su baskını, istasyon "
            "drenajı, gider ve mazgal tıkanıklığı, kanalizasyon taşması, peron "
            "tavan/duvar/zemin hasarı, çatlak, kolon, kiriş, tesisat, "
            "korkuluk, fayans dökülmesi, zeminde çukur ve çökme, devam eden "
            "inşaat faaliyetleri, iş güvenliği riskleri"
        ),
        "exclude": (
            "Rayın, makasın, traversin, balastın kendisi ve ray/hat drenajı "
            "'yol_yapisal' -- burası bina ve tünel yapısıdır, ray hattı değil. "
            "Yapısal sorunun sonucu oluşan kirlilik ayrı bir bildirimse "
            "'temizlik', ama bildirimde su/sızıntı/yapısal hasar geçiyorsa "
            "kategori her zaman burasıdır."
        ),
    },
}


# ---------------------------------------------------------------------------
# Intent (niyet) -- kategoriden BAGIMSIZ ikinci boyut
#
# Kategori "konu hangi teknik alana ait" sorusunu, intent ise "kullanici ne
# yapmak istiyor" sorusunu cevaplar. Ayni kategori farkli intent'lerle
# gelebilir: "asansor bozuk" (fault_report) ile "asansor ne zaman duzelecek"
# (information_request) ikisi de mekanik_istasyon'dur.
#
# Akis: INTENT -> CATEGORY -> ENTITIES -> PRIORITY -> ROUTING
# ---------------------------------------------------------------------------

INTENTS = {
    "fault_report": {
        "display": "Arıza Bildirimi",
        "scope": (
            "Teknik bir arızanın veya bozukluğun bildirilmesi -- bir ekipmanın "
            "çalışmaması, hasar görmesi veya beklenenden farklı davranması"
        ),
    },
    "incident_report": {
        "display": "Olay Bildirimi",
        "scope": (
            "Gerçekleşmekte olan veya gerçekleşmiş bir olayın bildirilmesi -- "
            "asayiş olayı, acil sağlık durumu, yangın, güvenlik tehdidi. "
            "Arızadan farkı: ekipman değil bir DURUM söz konusudur ve "
            "genellikle acil müdahale gerektirir"
        ),
    },
    "information_request": {
        "display": "Bilgi Talebi",
        "scope": (
            "Bir soru sorulması -- durumun ne zaman düzeleceği, seferin ne "
            "zaman geleceği, bir hattın çalışıp çalışmadığı. Cümle soru "
            "biçimindedir veya bilgi istemektedir"
        ),
    },
    "complaint": {
        "display": "Şikayet",
        "scope": (
            "Hizmet kalitesinden duyulan memnuniyetsizlik -- personelin "
            "ilgisizliği, beklemenin uzunluğu, kalabalık, genel rahatsızlık. "
            "Somut bir arıza bildirilmez, hizmetten şikayet edilir"
        ),
    },
    "suggestion": {
        "display": "Öneri",
        "scope": (
            "İyileştirme önerisi -- yeni bir düzenleme, ek ekipman veya "
            "işleyiş değişikliği talebi. Mevcut bir sorun değil, gelecekteki "
            "bir iyileştirme önerilir"
        ),
    },
}


# ---------------------------------------------------------------------------
# Oncelik (priority) -- kategoriden ve intent'ten BAGIMSIZ ucuncu boyut
#
# ILK SURUMDE P2/P3 SINIRI SAYIYA DAYANIYORDU ("birden fazla merdiven" P2,
# "tek merdiven" P3) ve model bunu ogrenemedi: P2 sinif F1 = 0.38, hatalarin
# cogu P2<->P3 arasindaydi. Iki tur bagimsiz etiketleme uyumu da dusuktu
# (bkz. src/oncelik_tutarlilik.py): ham uyum %69.8, kappa 0.584, P2'de %38.
#
# IKINCI SURUM (bu blok): "sefer/yolcu akisi aksiyor mu?" tek basina hala
# yoruma acikti -- "aksama" ne demek net degildi. MERDIVEN MANTIGINA
# gecildi: dort tanim YUKARIDAN ASAGIYA, BIRBIRINI DISLAYACAK sekilde
# siralanmis, her birinde tek bir EVET/HAYIR sorusu var:
#
#   1. Can guvenligi tehdidi mi?                              -> P1
#   2. Sefer durdu/iptal oldu MI, veya BIRDEN FAZLA ekipman   -> P2
#      ayni anda devre disi mi, veya yolcu FIZIKSEL OLARAK
#      gecemiyor mu?
#   3. TEK ekipman arizali ama yolcu ALTERNATIFLE devam        -> P3
#      edebiliyor mu?
#   4. Hicbir ARIZA yok, sadece gorunum/bilgi/oneri mi?        -> P4
#
# Sorular arka arkaya sorulur (P1 degilse P2'ye bak, o da degilse P3'e...),
# yani ayni bildirim iki soruya birden "evet" diyemez -- bu tasarimla
# amaclanan, P2/P3 arasindaki "aksiyor mu" belirsizligini somut olceklerle
# (sefer durdu mu / birden fazla mi / alternatif var mi) degistirmek.
#
# P1 ayrica KURAL ile de belirlenir (yangin, elektrik carpmasi, intihar...)
# -- bkz. PRIORITY_RULES asagida. Model sadece kuralin karar veremedigi
# bildirimleri siniflandirir.
# ---------------------------------------------------------------------------

PRIORITIES = {
    "P1": {
        "display": "Kritik",
        "color": "#dc2626",
        "scope": (
            "SORU 1 -- CAN GÜVENLİĞİ tehdidi var mı? Yangın, yoğun duman, "
            "elektrik çarpması riski, açıkta kalmış enerjili kablo, raylara "
            "kişi düşmesi veya atlaması, hat üzerinde tren güvenliğini tehdit "
            "eden nesne veya engel (kaya, cisim, çökme parçası), tren "
            "kapısının açık seyretmesi, fren sisteminin arızalı olması veya "
            "basıncının düşük olması, peronda düşme riski, su baskını, acil "
            "çıkış ve tahliye kapılarının çalışmaması, acil yardım/çağrı "
            "butonunun yanıt vermemesi, FİZİKSEL saldırı (darp, bıçak, "
            "silah, personele veya yolcuya yönelik fiili saldırı), şüpheli "
            "paket, hayati sağlık acil durumu, kendine zarar verme riski, "
            "yapısal çökme veya çökme riski. EVET ise P1, bu bildirim burada "
            "biter -- alttaki sorulara bakılmaz.\n"
            "AÇIKÇA P1 DEĞİL: mala yönelik ve şiddet İÇERMEYEN suçlar -- "
            "yankesicilik, hırsızlık, kayıp eşya, zorla para isteme (fiziksel "
            "şiddet yoksa), yasak madde kullanımı, dilencilik, sözlü sataşma. "
            "Bunlar guvenlik_asayis_olay KATEGORİSİNE girer ama önceliği "
            "P1 DEĞİL, olayın ciddiyetine göre P2'dir (müdahale gerektirir, "
            "can tehdidi yoktur) -- 'asayiş olayı = otomatik P1' VARSAYMA.\n"
            "AYRICA P1 DEĞİL: VARSAYIMSAL/KOŞULLU tehlike ifadeleri -- 'yangın "
            "ÇIKSA tüpe erişilemez', 'bir şey OLURSA acil çıkış kilitli', "
            "'yangın İHTİMALİNE karşı' gibi cümleler HENÜZ GERÇEKLEŞMEMİŞ bir "
            "riske karşı ÖNLEM EKSİKLİĞİ bildirir, gerçekleşmiş bir tehlike "
            "DEĞİLDİR. Bunlar P3 veya P4'tür (önlem eksikliği ciddiyetine "
            "göre). Sadece GERÇEKLEŞMİŞ veya ŞU AN gerçekleşmekte olan tehdit "
            "P1'dir -- 'yangın var', 'duman doldu', 'yanıyor' P1; 'yangın "
            "çıksa napcaz', 'tüpe erişim yok' (yangın olmadan) P1 DEĞİL."
        ),
    },
    "P2": {
        "display": "Yüksek",
        "color": "#ea580c",
        "scope": (
            "(P1 değilse) SORU 2 -- şu ÜÇ somut durumdan biri var mı? "
            "(a) Sefer DURDU, İPTAL edildi veya ciddi şekilde seyreltildi; "
            "(b) AYNI TÜRDEN İKİ VEYA DAHA FAZLA ekipman (iki+ merdiven, "
            "iki+ asansör, birden fazla turnike, PAKS) AYNI ANDA devre "
            "dışı; (c) yolcular FİZİKSEL OLARAK geçiş/giriş/çıkış "
            "YAPAMIYOR (turnikelerin tamamı kapalı, tüm girişler kapalı, "
            "istasyon kapatıldı), istasyonda ciddi su sızıntısı sefer "
            "hattını tehdit ediyor. Üçünden biri EVET ise P2 -- SORU 3'e "
            "bakılmaz. HİÇBİRİ değilse P3'e geç.\n"
            "(b) MADDESİ İÇİN DİKKAT: 'birden fazla' her zaman SAYIYLA "
            "yazılmaz -- 'hiçbiri çalışmıyor', 'bütün merdivenler durdu', "
            "'tamamı devre dışı', 'hepsi bozuk', 'cihazların hepsi aynı "
            "anda durmuş' gibi ifadeler de AYNI ANLAMA gelir ve P2'dir. "
            "'iki/üç/birden fazla' sadece örnek, tek geçerli ifade biçimi "
            "DEĞİL -- anlam olarak 'tek bir ekipman değil, birden çoğu' "
            "diyen her ifade bu maddeyi tetikler."
        ),
    },
    "P3": {
        "display": "Orta",
        "color": "#ca8a04",
        "scope": (
            "(P1 ve P2 değilse) SORU 3 -- TEK bir ekipmanın arızası var ve "
            "yolcu bu ekipman olmadan veya bekleyerek yolculuğuna DEVAM "
            "EDEBİLİYOR mu? Tek yürüyen merdiven/asansör/turnike/biletmatik "
            "arızası, birkaç aydınlatma lambasının yanmaması, klimanın "
            "çalışmaması, bir kameranın görüntü vermemesi, sinyalizasyonun "
            "sefer akışını DURDURMADAN aksatması. EVET (yolculuk mümkün) "
            "ise P3. Arıza YOKSA P4'e geç."
        ),
    },
    "P4": {
        "display": "Düşük",
        "color": "#65a30d",
        "scope": (
            "(P1, P2, P3 değilse) SORU 4 -- hiçbir ekipman ARIZASI yok mu, "
            "bildirim sadece görünüm/bilgi/öneri mi? Kirlilik ve temizlik "
            "talebi, hasarlı veya eksik tabela, kozmetik hasar, "
            "bilgilendirme eksikliği, küçük bakım talepleri, öneriler ve "
            "iyileştirme istekleri, bilgi talepleri, personelin ilgisizliği "
            "gibi arıza içermeyen şikayetler. Buraya kadar geldiyse zaten "
            "P4 -- başka soru yok."
        ),
    },
}


# P1 KURAL KATMANI -- oncelik tahmininin onunde calisir.
#
# NEDEN KURAL: P1 bildirimleri kacirmanin bedeli asimetriktir. Bir yangin
# bildirimini P3 sanmak kabul edilemez; tersi (P3'u P1 sanmak) sadece gereksiz
# aciliyet yaratir. Model %61 dogrulukla calisirken bu riski tasiyamayiz.
#
# Bu desenler metinde gecerse oncelik KOSULSUZ P1 olur ve modelin tahmini
# yok sayilir. Desenler normalize edilmis (kucuk harf + aksansiz) metinde
# aranir. Dar ve kesin tutuldu: her biri tek basina can guvenligi tehdidi
# anlamina gelen ifadeler. "Genis ve gurultulu kural yerine dar ve kesin
# kural" ilkesi (bkz. YABANCI bayragi dersi).
PRIORITY_RULES = [
    # "yangin" tek basina yeterli degil -- iki yanlis pozitif kaynagi var:
    # (1) ekipman adi ("yangin tupu/sondurme/algilama/dolabi/merdiveni" bir
    #     OLAY degil, cihaz ismi); (2) kosullu/varsayimsal cumle ("yangin
    #     CIKSA/OLURSA/ihtimaline karsi" henuz gerceklesmemis bir risk).
    # Ikisi de negatif bakis (lookahead) ile disariya alindi. 23 Agu 2026,
    # bagimsiz test setinde bulundu: "yangin tupu... yangin CIKSA tupe
    # erisim engellenmis" (gercek P4) modelde/kuralda P1 cikiyordu.
    (r"\byangin\b(?!\s*(tup|sondur|algila|dolab|merdiven|ciksa|cikarsa|"
     r"olursa|olsa|ihtimal))|\balev\b|\bates\b(?! kes)", "yangın"),
    (r"yogun duman|duman doldu|duman cikiyor|duman var", "yoğun duman"),
    (r"elektrik carp|akim carp|carpilma riski|carpilacak", "elektrik çarpması riski"),
    (r"raya atla|raylara atla|raya dus|raylara dus|ray uzerinde kisi", "raylara kişi"),
    (r"intihar|kendine zarar|kendini asag", "intihar riski"),
    (r"supheli paket|supheli canta|supheli kutu", "şüpheli paket"),
    (r"bicak cek|silah|saldiri var|saldirdi|fiili saldiri|saldiriya ugra|"
     r"saldirida bulun|darp edildi|darbedildi", "fiziksel saldırı"),
    (r"bayil|kalp krizi|nefes alamiyor|bilinci kapali|hayati tehlike", "sağlık acili"),
    (r"cokme riski|cokuyor|cokmus|tavan cok", "yapısal çökme"),
    (r"su baskini|su basti|sel basti", "su baskını"),
    (r"tahliye kapisi acilmiyor|acil cikis kilitli|acil cikis kapali",
     "acil çıkış engeli"),
    # Bu iki kural src/oncelik_tutarlilik.py olcumunde bulundu: birinci tur
    # etiketleme bunlari kacirip P2/P3 vermisti, ikinci tur (ayni model,
    # farkli cagri) P1'e duzeltti -- yani config metni dogru okunuyor ama
    # LLM her seferinde ayni sekilde yakalamiyordu. Kural katmani bu
    # tutarsizligi ortadan kaldirir.
    (r"kaya parcasi|yabanci cisim|hat\w*\s+uzerinde.{0,25}(kaya|cisim|engel|"
     r"nesne)|yolu.{0,15}kapat|raylar\w*.{0,15}kapat|tren gecemiyo",
     "hat üzerinde engel"),
    (r"acil yardim butonu.*(yanit vermiyor|calismiyor|bozuk)|"
     r"acil cagri butonu.*(yanit vermiyor|calismiyor|bozuk)",
     "acil yardım butonu arızası"),
    (r"fren basinci dusuk|fren tutmuyor|fren arizali|fren calismiyor",
     "fren arızası"),
]

CATEGORY_KEYS = list(CATEGORIES.keys())
NUM_LABELS = len(CATEGORY_KEYS)

LABEL2ID = {k: i for i, k in enumerate(CATEGORY_KEYS)}
ID2LABEL = {i: k for k, i in LABEL2ID.items()}
DISPLAY_NAME = {k: v["display"] for k, v in CATEGORIES.items()}
CATEGORY_COLOR = {k: v["color"] for k, v in CATEGORIES.items()}

# Intent ve oncelik, kategoriyle ayni desende turetilir. Model bu uc boyutu
# TEK govde uzerinde ayri siniflandirma basliklariyla ogrenir (multi-task):
# ortak BERTurk temsili, uc ayri cikti katmani. Ayri model egitmeye gore hem
# hizli hem kucuk, ustelik boyutlar arasi ortak sinyal paylasiliyor.
INTENT_KEYS = list(INTENTS.keys())
NUM_INTENTS = len(INTENT_KEYS)
INTENT2ID = {k: i for i, k in enumerate(INTENT_KEYS)}
ID2INTENT = {i: k for k, i in INTENT2ID.items()}
INTENT_DISPLAY = {k: v["display"] for k, v in INTENTS.items()}

PRIORITY_KEYS = list(PRIORITIES.keys())
NUM_PRIORITIES = len(PRIORITY_KEYS)
PRIORITY2ID = {k: i for i, k in enumerate(PRIORITY_KEYS)}
ID2PRIORITY = {i: k for k, i in PRIORITY2ID.items()}
PRIORITY_DISPLAY = {k: v["display"] for k, v in PRIORITIES.items()}
PRIORITY_COLOR = {k: v["color"] for k, v in PRIORITIES.items()}

# Kategori -> yonlendirilecek birim. Simdilik kategori anahtarinin buyuk harfli
# hali; kurumun gercek birim kodlari netlestiginde burasi degisir, cagiran
# kodun hicbiri degismez.
ROUTING_UNIT = {k: k.upper() for k in CATEGORY_KEYS}


# ---------------------------------------------------------------------------
# Veri uretim ayarlari
# ---------------------------------------------------------------------------

SEED_PER_CATEGORY = 12      # few-shot yemi
GOLD_PER_CATEGORY = 10      # bozulmamis test seti
TARGET_PER_CATEGORY = 200   # nihai egitim verisi (cogaltma sonrasi)

MIN_CHARS = 8               # bundan kisa bildirimler atilir
MAX_CHARS = 300             # bundan uzun bildirimler atilir
# Benzerlik esikleri. IKI AYRI DEGER, cunku esik iki farkli isi goruyor ve
# hata maliyetleri simetrik degil (19 Agu 2026 kalibrasyonu):
#
#   URETIM (generate_data/generate_seed -- yeni kaydi reddet):
#     yanlis reddetme -> iyi bir cumle bosa gider, kota harcanir
#     kacirma         -> veri biraz tekrarli olur
#     Maliyetler dengeli, 0.85 uygun.
#
#   BOLME (preprocess -- kumeleme):
#     yanlis birlestirme -> iki kayit ayni bolmeye duser, kucuk cesitlilik kaybi
#     kacirma            -> ayni cumlenin varyasyonu hem train hem test'e duser,
#                           METRIK SISER (sahte yuksek dogruluk)
#     Kacirmanin bedeli cok daha agir, o yuzden daha agresif: 0.80.
#
# Kalibrasyon olcumu (1600 kayit, ayni kategori icinde):
#   0.85 -> 1 cift birlesti | 0.82 -> 8 | 0.80 -> 23 | 0.78 -> 39 (kumeler 5'e
#   zincirlenmeye basliyor) | 0.75 -> 88 (fazla agresif)
# 0.80-0.85 bandinda gercek anlamsal kopyalar oldugu elle dogrulandi, orn:
#   "Taksim istasyonunda 4 numarali vagondaki yolcu anons cihazi ses vermiyor."
#   "Yolcu anons cihazi ses vermiyor 4. vagon"                        (0.843)
# Ayni bantta gercekten FARKLI arizalar da var (olcut sozcuksel, anlamsal degil):
#   "makinist kabini sag tarafi ayna kirik" / "makinist kabini saati durmus"
#                                                                     (0.804)
# 0.80'de kume boyutu 2'de kaliyor (zincirleme yok), bedel 23 kayit / 1600.
NEAR_DUP_THRESHOLD = 0.85   # uretimde yeni kayit reddi
CLUSTER_THRESHOLD = 0.80    # preprocess'te split oncesi kumeleme
NEAR_DUP_JACCARD = 0.55     # kelime kumesi ortusme esigi (SequenceMatcher yaninda)

# Bildirimlerin yazim stilleri. Gercek personel her zaman duzgun yazmaz.
STYLE_VARIANTS = {
    "standart": (
        "Düzgün yazılmış, kurallı tam cümle, noktalama doğru. Resmi bildirim "
        "dili. UZUNLUK: 8-18 kelime."
    ),
    "devrik": (
        "Acele yazılmış, KISA ve eksiltili. Yüklem başa gelebilir, özne veya "
        "tamlayan düşebilir, noktalama eksik olabilir. UZUNLUK: 4-9 kelime. "
        "DOĞRU örnek: 'Yürüyen merdiven durdu 2. peron'. "
        "DOĞRU örnek: 'Kapı açılmıyor A2 vagon'. "
        "YANLIŞ örnek (bunu ÜRETME, çok uzun ve edebi devrik): "
        "'Kırılmış dönme kolu Mecidiyeköy ana bilet holü 5 numaralı "
        "turnikenin, fiziki geçişe engel duruyor.'"
    ),
    "yazim_yanlisi": (
        "Türkçe karakter eksikliği (ç, ğ, ı, ö, ş, ü yerine ASCII), harf "
        "düşmesi, klavye hatası. Anlam anlaşılır kalmalı. UZUNLUK: 5-14 kelime. "
        "Örnek: 'asansor calismiyo', 'elektirik kesildi 3. perondaki'."
    ),
    "cok_kisa": (
        "Telgraf tarzı, sadece ekipman + belirti. UZUNLUK: 3-6 kelime. "
        "Örnek: 'Turnike 3 bozuk', 'Peronda su var'."
    ),
}

STYLE_KEYS = list(STYLE_VARIANTS.keys())

# Prompt'lara enjekte edilecek slot degerleri -- cesitliligi prompt seviyesinde
# zorlamak icin. Cogaltma asamasinda her cagrida rastgele secilir.
SLOT_VALUES = {
    "istasyon": [
        "Yenikapı", "Taksim", "Şişhane", "Levent", "Kadıköy", "Mecidiyeköy",
        "Vezneciler", "Kartal", "Ataköy", "Bağcılar", "Gayrettepe", "Hacıosman",
        "Uzunçayır", "Bostancı", "Kirazlı", "Esenler", "Sanayi Mahallesi",
        "Şişli", "Üsküdar", "Topkapı", "Şirinevler",
    ],
    "konum": [
        "1. peron", "2. peron", "kuzey giriş", "güney çıkış", "gişe önü",
        "alt kat", "üst kat", "koridor", "bilet holü", "tünel ağzı",
        "personel kapısı", "asansör önü", "turnike bölgesi",
    ],
    "zaman": [
        "sabah vardiyasında", "gece vardiyasında", "akşam yoğun saatte",
        "öğle saatlerinde", "servis başlangıcında", "servis sonunda",
        "hafta sonu", "az önce", "bu sabah 07:20'de",
    ],
    "aciliyet": [
        "acil müdahale gerekiyor", "yolcu güvenliği riskli",
        "sefer aksıyor", "şimdilik idare ediliyor",
        "tekrarlayan bir arıza", "ilk defa oluyor", "bilgi amaçlı",
    ],
}


# ---------------------------------------------------------------------------
# LLM saglayici ayarlari
#
# GENEL POLITIKA (23 Agu 2026): ONEMLI islerde Nemotron (OpenRouter), DIGER
# islerde gemma4:cloud (Ollama).
#   ONEMLI  = seed/gold uretimi -- kucuk hacimli (12-10/kategori) ama few-shot
#             yemi ve degerlendirme tabani olarak butun projeyi etkiliyor.
#             SEED_PROVIDER = "openrouter" (asagida).
#   DIGER   = coklu boyutlu etiketleme (relabel/generate_missing/
#             oncelik_tutarlilik) -- yuksek hacimli (1000+ kayit), hiz ve
#             kota-sizlik burada Nemotron'un kalitesinden daha degerli.
#             OLLAMA_MODEL = "gemma4:cloud" (asagida), varsayilan saglayici.
# Gerekce: gemma4:cloud relabel gorevinde qwen2.5:14b'yi acik farkla gecti
# (bkz. OLLAMA_MODEL yorumu) ve kota siniri yok; Nemotron kalitede guclu ama
# ~50 istek/gun kotasi + yavasligi (120 kayit ~8 dk) yuksek hacimli islerde
# pratik degil. Groq denendi (once llama-3.3-70b-versatile'in kataloktan
# kaldirildigi, sonra tek alternatif gpt-oss-120b'nin 15+ kayitlik
# partilerde JSON semasini bozdugu goruldu) -- bu proje icin kullanisli
# bulunmadi.
# ---------------------------------------------------------------------------

# Seed ve gold uretimi icin: "gemini" | "claude" | "groq" | "openrouter"
# NOT (13 Agu 2026): karsilastirma sonucu OpenRouter/Nemotron 3 Ultra kazandi
# (seed %17, gold %9 isaretli -- Gemini/Groq'tan daha iyi, ustelik ucretsiz).
SEED_PROVIDER = "openrouter"

# NOT: gemini-2.5-flash 2026 itibariyle YENI kullanicilara kapatildi; API
# "no longer available to new users" hatasi doner. Bu hata yanlislikla
# "gecersiz API anahtari" gibi gorunebiliyor (SDK 400 INVALID_ARGUMENT
# donduruyor, dogrudan REST cagrisi ise net 404 mesaji veriyor) -- anahtari
# suclamadan once model listesini canli sorgula (Genel Ilke 4).
# gemini-3.7-flash uretim yukunde surekli 503 ("high demand") donduruyordu;
# 3.6 ayni istekleri sorunsuz karsiliyor.
GEMINI_MODEL = "gemini-3.1-flash-lite"        # AI Studio'da guncel id'yi teyit et
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Groq: kredi karti gerektirmez, OpenAI-uyumlu API, genis ucretsiz kota
# (30 istek/dk, 14.400 istek/gun civari -- modele gore degisir).
# NOT (13 Agu 2026): llama-3.3-70b-versatile bu proje icin YETERSIZ cikti.
# NOT (23 Agu 2026): llama-3.3-70b-versatile canli katalogdan TAMAMEN
# KALKMIS (Groq'ta artik hic Llama sohbet modeli yok, sadece prompt-guard
# gibi kucuk yardimci modeller). En buyuk genel amacli secenek
# openai/gpt-oss-120b'ye gecildi, ama PRATIK DEGIL: relabel gorevinde
# (kategori+intent+oncelik JSON'u) 10 kayitlik partide calisiyor, 15+
# kayitta JSON semasini bozup 400 hatasi veriyor -- bu projenin standart
# BATCH=40'iyla uyumsuz, kullanmak icin ozel kucuk-batch mantigi gerekir.
# Bu yuzden POLITIKA disinda tutuldu (bkz. "GENEL POLITIKA" yorumu yukarida):
# Nemotron (onemli isler) + gemma4:cloud (diger isler) yeterli bulundu.
GROQ_MODEL = "openai/gpt-oss-120b"

# OpenRouter: kredi karti istemeyen ikinci ucretsiz secenek (gunde 50 istek).
# Katalog surekli degisiyor, sadece acik agirlikli modeller ucretsiz.
# NOT (13 Agu 2026): canli listede gpt-oss-120b yoktu (sadece 20b), en genis
# olceki secenek NVIDIA Nemotron 3 Ultra (550B toplam / 55B aktif param) --
# talimat takibinde guclu (IFBench 81.7), coklu dil destekli. Turkce'de
# ozel olcum yok, ama olcek avantaji var.
OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

LLM_TEMPERATURE = 1.0       # cesitlilik istiyoruz, dogruluk degil
LLM_MAX_RETRIES = 3


# --- Cogaltma (Adim 2b) ------------------------------------------------------
# Karar (18 Agu 2026): HIBRIT strateji. OpenRouter/Nemotron kaliteyi belirledi
# ama ucretsiz katman ~50 istek/gun; 1600 ornek icin bu yetmiyor. Bu yuzden
# birincil saglayici OpenRouter, KALICI hata (kota/429/401) gelince kalan is
# otomatik olarak yerel Ollama'ya devrediliyor. Boylece kaliteli modelden
# alabildigimiz kadar aliyoruz, kalanini bedelsiz yerelde tamamliyoruz.
# Uretilen her kaydin 'kaynak' alani hangi modelden geldigini tasir, boylece
# iki modelin katkisi sonradan ayrilabilir (rapor icin de kullanisli).
AMPLIFY_PROVIDER = "hybrid"     # "hybrid" | "openrouter" | "ollama"

OLLAMA_HOST = "http://localhost:11434"

# NOT (23 Agu 2026): qwen2.5:14b TAMAMEN BIRAKILDI, tek Ollama modeli
# gemma4:cloud oldu. Once ETIKETLEME rolunde kiyaslandi (120 kayitlik
# referans set, bulut-etiketli kayitlarla kiyas):
#     model           kategori   intent   oncelik      sure (120 kayit)
#     qwen2.5:14b       %62.4     %71.8     %36.8      10 dk  9 sn
#     gemma4:cloud      %90.8     %94.2     %58.3          41 sn
# Sonra URETIM rolunde de test edildi: gemma4:cloud ile Istasyon Guvenligi
# kategorisi icin 200 kayit uretildi (bu kategori 113 kayitla en zayif
# kategoriydi, F1 0.6154), elle okundu -- qwen'in bilinen zayifligi olan
# uydurma istasyon adi/teknik terim HIC gorulmedi (Adim 2b'de qwen
# "marmaraisi", "yersenlik" gibi terimler uydurmustu). gemma4:cloud iki
# rolde de UC BOYUTTA ONDE ve on be kat hizli -- qwen'i tutmak icin bir
# gerekce kalmadi.
#
# Tek degisken yeterli: iki rol (uretim + etiketleme) artik ayni modeli
# kullaniyor, ayri OLLAMA_LABEL_MODEL degiskeni gereksizdi ve silindi.
OLLAMA_MODEL = "gemma4:cloud"

OLLAMA_TIMEOUT = 300            # 14B model Apple Silicon'da yavas olabilir

# Ollama'nin varsayilan baglam penceresi 2048 token. Cogaltma prompt'u
# (kategori kapsami + stil tanimi + few-shot + "bunlari tekrarlama" listesi)
# tek basina bunun buyuk kismini yiyor, cikartiya yer kalmiyor: model 25 ornek
# istenmesine ragmen 1-2 ornek dondurup kesiliyordu. Acikca genisletiyoruz.
# qwen2.5:14b 32768 token destekliyor, 8192 hem bol hem 16GB RAM'de guvenli.
OLLAMA_NUM_CTX = 8192
OLLAMA_NUM_PREDICT = 4096

# Her LLM cagrisinda tek (kategori, stil) ikilisi icin kac ornek istenecegi.
# Tek cagrida tek stil istemek uzunluk kuralina uyumu ciddi artiriyor: model
# ayni anda 4 farkli uzunluk araligini yonetmek zorunda kalmiyor.
#
# NOT (18 Agu 2026): 25'ten 40'a cikarildi. Baglayici kisit ornek sayisi degil
# CAGRI sayisi: OpenRouter ucretsiz katmani ~50 istek/gun ve 25'lik partilerle
# 1600 ornek 64 cagri gerektiriyordu -- yani son ~350 kayit zorunlu olarak
# Ollama'ya kaliyordu. 40'lik partiyle ~40 cagri yetiyor ve veri tek gunde
# tamamen Nemotron'dan gelebiliyor. Olcum: Nemotron 40 kaydi 4 cagride,
# %5 isaretli oranla uretti; qwen2.5:14b ayni isi 7 cagride %18 isaretli
# oranla ve uydurma istasyon adlariyla yapti.
AMPLIFY_BATCH_SIZE = 40

# Cogaltmada few-shot olarak kac seed ornegi gosterilecek ve modele "bunlari
# tekrar etme" diye kac mevcut ornek hatirlatilacagi.
AMPLIFY_FEWSHOT_N = 6
AMPLIFY_AVOID_N = 12


# ---------------------------------------------------------------------------
# Egitim hiperparametreleri
# ---------------------------------------------------------------------------

BASE_MODEL = "dbmdz/bert-base-turkish-cased"

MAX_LENGTH = 64             # ariza bildirimleri kisa; 64 token fazlasiyla yeter
NUM_EPOCHS = 12

# Early stopping: validation KAYBI (loss) art arda EARLY_STOPPING_PATIENCE
# epoch boyunca iyilesmezse egitim NUM_EPOCHS'a ulasmadan durur.
#
# DIKKAT -- bu, model_kaydet() secimiyle AYNI SEY DEGIL: en iyi checkpoint
# hala uc gorevin ORTALAMA macro-F1'ine gore seciliyor (val_kayip'e gore
# degil). Sebep: F1 asil basari kriteri, val_kayip sadece "asiri ogrenmeye
# basladi mi" sinyali icin izleniyor -- ikisi bazen ayni epoch'ta pik
# yapmaz (bu projede de val_kayip epoch 6-7'den sonra yukselirken F1 hala
# artabiliyordu, bkz. egitim_ozeti.json gecmisi).
EARLY_STOPPING_PATIENCE = 3
BATCH_SIZE = 16

# DIKKAT (19 Agu 2026): burada onceden 2e-5 yaziyordu ve model OGRENMIYORDU.
# 2e-5, BERT'i TAM fine-tuning ederken kullanilan standart degerdir; biz LoRA
# kullaniyoruz. LoRA'da parametrelerin sadece %0.54'u (595.976) egitiliyor,
# adaptorler sifirdan basliyor ve siniflandirma basligi rastgele baslatiliyor
# -- bu kadar kucuk bir ogrenme hiziyla agirliklar anlamli mesafe kat edemiyor.
# Olculdu (5 epoch, val macro-F1):
#     2e-5 -> 0.134   (kayip 2.146 -> 2.073; rastgele seviye ln(8)=2.079)
#     1e-4 -> 0.393
#     3e-4 -> 0.850
#     5e-4 -> 0.875
# 15 epoch'ta: 5e-4 -> 0.930 (epoch 13), 1e-3 -> 0.938 (epoch 11).
# Ikisi arasindaki fark val setinde ~1 ornek (n=160), yani gurultu icinde.
# 5e-4 secildi: ayni sonucu daha yumusak bir egriyle veriyor.
# Ders: hiperparametreyi literaturden kopyalamak yetmiyor, EGITIM YONTEMINE
# gore ayarlamak gerekiyor.
LEARNING_RATE = 5e-4
WEIGHT_DECAY = 0.01
WARMUP_RATIO = 0.1
SEED = 42

TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10

# Egitimde aksansiz (ASCII'ye katlanmis) kopyalar da eklensin mi?
#
# NEDEN (19 Agu 2026, nedensel olarak olculdu): test+gold'daki aksan iceren
# 173 kaydin aksanlari kaldirilip yeniden tahmin edildi -- ICERIK AYNI, sadece
# ç/ğ/ı/ö/ş/ü duruyor:
#     orijinal      157/173 = 0.9075
#     ASCII katlanmis 146/173 = 0.8439      -> 6.4 puan dusus
# Mekanizma BERTurk tokenizer'inda gorunuyor:
#     "asansör" -> 1 parca  ['asansör']
#     "asansor" -> 3 parca  ['asa', '##ns', '##or']
# Aksan dusunce kelime anlamsiz alt-parcalara boluuyor.
#
# Gercek hayatta personel Ingilizce klavyeyle yazip aksan dusurebiliyor
# (config'in kendi "Onemli tasarim karari" notu da bunu soyluyor), yani bu
# dayaniklilik sus degil gereklilik.
#
# Cozum: train'deki aksanli kayitlarin ASCII kopyalari egitime eklenir. Model
# "güvenlik" ile "guvenlik"in ayni sey oldugunu ogrenir. Bedava (API yok).
# SIZINTI RISKI YOK: preprocess'teki kumeleme zaten aksan-duyarsiz calisiyor
# (review.normalize aksanlari kaldiriyor), yani bir train kaydinin ASCII
# kopyasi test'teki bir kayitla eslesiyorsa o ikisi zaten ayni kumededir.
AUGMENT_ASCII_FOLD = True

# seed.jsonl (93 elle gozden gecirilmis kayit) egitim havuzuna katilsin mi?
#
# OLCULDU (19 Agu 2026, kosul basina 3 tohum, GOLD uzerinden -- gold iki
# kosulda da ayni oldugu icin tek gecerli karsilastirma o):
#   kosul          gold macro F1 (3 tohum)        ortalama  aralik  min sinif F1
#   kapali         0.9247 0.9105 0.9624            0.9325   0.0519  0.750-0.900
#   acik           0.9497 0.9384 0.9371            0.9417   0.0126  0.818-0.889
#
# ORTALAMA KAZANC KANITLANMADI: +0.0092, baseline'in kendi salinimi 0.0519.
# Tek kosuyla olculdugunde "+0.025 kazanc" gibi gorunuyordu -- gurultuymus.
#
# Yine de ACIK secildi, sebebi ortalama degil TABAN: kapaliyken en kotu kosuda
# en dusuk sinif F1 = 0.7500, yani basari kriterinin (0.75) tam sinirinda; bir
# kayit daha kaysa kriter duserdi. Acikken en kotu durum 0.8182. Ayrica 93
# temiz kayit bosa gitmiyor ve maliyeti sifir.
#
# Sizinti riski yok: cogaltma seed'den uretildigi icin seed kayitlari
# cogaltilmislarla yakin kopya, ama preprocess'teki kumeleme bunlari ayni
# bolmede tutuyor (olculdu: near_dup_train_test_AYNI_kategori = 0).
INCLUDE_SEED_IN_TRAINING = True

# PEFT / LoRA
USE_LORA = True
LORA_R = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.1
LORA_TARGET_MODULES = ["query", "value"]

# Basari kriterleri
TARGET_ACCURACY = 0.85
TARGET_MACRO_F1 = 0.82
MIN_PER_CLASS_F1 = 0.75


# ---------------------------------------------------------------------------
# Servis ayarlari
# ---------------------------------------------------------------------------

# Bu esigin altinda kategori kesin atanmaz, arayuzde manuel inceleme uyarisi
# cikar. k-fold OUT-OF-FOLD ile kalibre edildi (bkz. src/calibrate.py).
#
# Neden OOF: esigi test'e bakarak secmek test setini karar surecine sokar;
# val.csv ise epoch seciminde kullanildigi icin model orada fazla emin ve
# sadece 9 hata iceriyor. OOF ile hata sayisi ~90-100.
#
# IKI KALIBRASYON YAPILDI (ikincisi seed egitime katildiktan sonra):
#   esik   1. kalibrasyon (1280 kayit, 102 hata)   2. kalibrasyon (1340, 92)
#          precision / recall                       precision / recall
#   0.60     0.543 / 0.245                            0.581 / 0.196
#   0.70     0.493 / 0.363                            0.529 / 0.293
#   0.75     0.500 / 0.461   <- secilen               0.478 / 0.359
#   0.80     0.430 / 0.480                            0.429 / 0.391
#
# DURUST NOT: 0.75 ilk kalibrasyonda 0.70'i DOMINE ediyordu (ayni precision,
# daha yuksek recall). Ikinci kalibrasyonda bu gecerli DEGIL -- 0.70 daha
# yuksek precision veriyor. Sebep: model iyilesti (OOF dogruluk 0.9203 ->
# 0.9313) ama hatalarinda daha emin (yanlislarda ort. guven 0.773 -> 0.811),
# yani guven sinyali zayifladi. Daha iyi model, daha zor ayirt edilen hatalar.
#
# 0.75'te birakildi: ~%5 trafik, hatalarin %36'si, kurtarma/bosuna orani ~1:1
# -- yorumlanabilir bir calisma noktasi. Ama artik "domine ediyor" degil,
# "makul bir denge" gerekcesiyle.
CONFIDENCE_THRESHOLD = 0.75
LOW_CONFIDENCE_MESSAGE = "Düşük Güven: Manuel İnceleme Önerilir"

# --- Ikincil kategori (taksonomi sinir sorunlarina genel cozum) --------------
# Bazi bildirimler GERCEKTEN iki kategoriye birden girer. Somut ornek:
# "Acil tahliye anonsu yogun saatlerde peronda net duyulamiyor." -- config'in
# kendi metnine gore guvenlik_emniyet ("anons ile tahliye") ve yolcu_operasyon
# ("anons yapilmamasi/yanlis anons") kapsamlarinin IKISINE de giriyor.
#
# Bunu taksonomiye sinir kurallari yazarak cozmek olceklenmiyor: 8 kategoride
# 28 cift var ve gercek veriye gecince bugun bilmedigimiz yenileri cikacak.
# Bunun yerine modelin ZATEN urettigi bilgiyi kullaniyoruz: marj (top1-top2)
# kucukse model iki kategori arasinda kararsiz demektir.
#
# Olculdu: top-1 dogruluk 0.913/0.925 iken TOP-2 dogruluk 0.963/0.975.
#
# KALIBRE EDILDI — k-fold OOF. Kurtarma/bosuna orani, iki kalibrasyon:
#   marj   1. (102 hata)   2. (92 hata)
#   0.20      0.71            1.44
#   0.30      0.80  <- tepe   0.93   <- SECILEN
#   0.40      0.71            1.11   <- tepe
#   0.50      0.68            0.81
#
# DIKKAT -- TEPE NOKTASI YER DEGISTIRDI. Ilk kalibrasyonda 0.30, ikincisinde
# 0.40 tepe veriyor. Yeni veriye bakip 0.40'a cekmek, gurultulu bir egrinin
# tepesini kovalamak olurdu -- bu projede tam da bu hata uc kez yapildi
# (bkz. CLAUDE.md "Tohum varyansi"). Iki kalibrasyonun ORTAK soyledigi:
# 0.20-0.40 bandi iyi, 0.50'den sonra bozuluyor. Bundan fazlasi bu veri
# hacmiyle sabitlenemiyor.
#
# 0.30'da birakildi. Onceki deger 0.40 idi ve GOLD'un 8 hatasina bakilarak
# "oran 4.0" diye kaydedilmisti; OOF tabaninda gercek oran ~0.8-1.1 cikti.
MARGIN_THRESHOLD = 0.30
SECONDARY_CATEGORY_MESSAGE = "Sınırda Bildirim: İkinci Kategori de Değerlendirilmeli"

API_HOST = "0.0.0.0"
API_PORT = int(os.environ.get("API_PORT", "8001"))

# CORS izinli kaynaklar. Prototipte allow_origins=["*"] idi; bu, herhangi bir
# web sitesinin tarayici uzerinden bu API'ye istek atabilmesi demek. Ic agda
# calisan bir prototipte kabul edilebilir ama kuruma entegrasyonda acik kapi.
#
# Varsayilan artik SADECE yerel gelistirme sunuculari -- eski Vite frontend'i
# rayli_ariza_tespiti ile birlesme sirasinda kaldirildi, ortak Next.js
# dashboard'u (bkz. ../web/) tek istemci. Uretimde ortam degiskeniyle
# daraltilir/genisletilir:
#     CORS_ORIGINS="https://ariza.metro.istanbul" uvicorn backend.main:app
CORS_ORIGINS = [
    "http://localhost:3000",      # Next.js dashboard (../web/)
    "http://127.0.0.1:3000",
]


# ---------------------------------------------------------------------------
# Yapisal cikarim (Adim 7) -- kurallı extraction sozlukleri
#
# Amac: siniflandirmayi "incident parsing" seviyesine cikarmak.
#   "M4 Unalan'da yuruyen merdiven cok ses yapiyor"
#   -> {category, line, station, equipment, symptom, confidence}
#
# Sozlukler burada, cunku config tek dogruluk kaynagi. Kategori kapsamlari
# (scope) zaten ekipman adlarini sayiyor; asagidaki EQUIPMENT listesi buyuk
# olcude oradan turetildi, sadece ekipman OLMAYANLAR (olay/belirti ifadeleri)
# ayiklandi.
# ---------------------------------------------------------------------------

# Hat kodu. Olculdu: bildirimlerin sadece ~%6'sinda hat kodu geciyor, yani bu
# alan pratikte cogu zaman None doner -- bu bir eksiklik degil, verinin dogasi.
LINE_PATTERN = r"\b(M\d{1,2}[AB]?|T\d|F\d|Marmaray)\b"

# Istasyon TANIMA listesi. SLOT_VALUES["istasyon"]'dan AYRIDIR ve onu kapsar:
# oradaki 21 ad URETIM icin (cesitlilik enjeksiyonu), buradaki liste TANIMA
# icin. Uretilen veride config listesi disinda gercek istasyon adlari da
# ciktigi icin (Kozyatagi, Aksaray, Sogutlucesme...) tanima listesi daha genis.
STATIONS = [
    # SLOT_VALUES ile ortak olanlar
    "Yenikapı", "Taksim", "Şişhane", "Levent", "Kadıköy", "Mecidiyeköy",
    "Vezneciler", "Kartal", "Ataköy", "Bağcılar", "Gayrettepe", "Hacıosman",
    "Uzunçayır", "Bostancı", "Kirazlı", "Esenler", "Sanayi Mahallesi",
    "Şişli", "Üsküdar", "Topkapı", "Şirinevler",
    # Uretilen veride gecen diger gercek istasyonlar
    "Kozyatağı", "Aksaray", "Mahmutbey", "Maltepe", "Göztepe", "Seyrantepe",
    "Ataşehir", "Kağıthane", "Pendik", "Dudullu", "Tavşantepe", "Ümraniye",
    "Haliç", "Merter", "Söğütlüçeşme", "Ayrılıkçeşmesi", "Ayrılık Çeşmesi",
    "Olimpiyat", "Huzurevi", "Yenisahra", "Bakırköy", "Zeytinburnu",
    "Atatürk Havalimanı", "Otogar", "Ünalan", "Acıbadem", "Yenibosna",
    "Çekmeköy", "Sancaktepe", "Osmanbey", "Beşiktaş", "Boğaziçi Üniversitesi",
]


# Istasyon ICINDEKI konum desenleri: (regex, cikti_bicimi). Normalize edilmis
# (kucuk harf, aksansiz) metinde aranir. Sirali denenir -- ustteki daha
# spesifik desenler once eslesmeli.
#
# Neden ayri bir alan: bir istasyonda ayni ekipmandan birden fazla var. Is
# emrine "Kadikoy'de merdiven bozuk" yazmak yetmez, hangi merdiven oldugu
# gerekir. Metro Istanbul'un kendi kayit sisteminde de bu alan ayri tutuluyor.
LOCATION_PATTERNS = [
    # NOT: asansor/merdiven/turnike/pano bilerek DISLANDI -- bunlar ayni
    # zamanda EQUIPMENT sozlugunde birebir gecen kelimeler. "3 numarali
    # asansor" cogu zaman "asansor #3" (yani ekipmanin KENDISI, hangi
    # ornek oldugunu belirtiyor) demektir; bu kelimeler buraya eklenirse
    # _konumu_maskele tum ifadeyi (ekipman kelimesi dahil) metinden silip
    # ekipman_bul()'un ayni kelimeyi bulmasini engelliyordu (gercek hata,
    # bkz. CLAUDE.md Adim 11). "X numarali asansorun YANINDAKI Y" gibi asil
    # konum-belirteci kullanimlar zaten asagidaki ayri "yanindaki/oradaki"
    # deseniyle yakalaniyor.
    (r"(\d+)\s*(?:numarali|nolu|no\.?)\s*(giris|cikis|peron|kapi|vagon)",
     "{0} numaralı {1}"),
    (r"(\d+)\s*\.\s*(peron|kat|vagon|giris|cikis)", "{0}. {1}"),
    (r"(kuzey|guney|dogu|bati)\s*(giris|cikis|peron|kapi)", "{0} {1}"),
    # Genel kalip: "<ekipman>in yanindaki/oradaki <asil ekipman>". Ilk ekipman
    # KONUM belirtiyor, asil ekipman sonra geliyor. Bu yakalanmazsa ekipman
    # aramasi ilk (yanlis) ekipmani secer.
    (r"(asansor|turnike|merdiven|gise|kapi|peron)\w*\s*"
     r"(?:yanindaki|oradaki|civarindaki|onundeki|karsisindaki|arkasindaki)",
     "{0} yanı"),
    # "turnikelerin oradaki/yanindaki" gibi cogul+ilgec kaliplari da konum
    # belirtir; bunlar yakalanmazsa ekipman aramasi "turnike"yi ekipman sanar.
    (r"turnikeler?(?:in|den)?\s*(?:oradaki|yanindaki|civarindaki|onundeki|"
     r"orada|yaninda|civarinda|onunde|tarafindaki)", "turnike bölgesi"),
    (r"turnike (?:bolgesi|kati|onu|civari|orasi|tarafi)", "turnike bölgesi"),
    (r"bilet (?:holu|gisesi|satis)", "bilet holü"),
    (r"gise (?:onu|civari|tarafi)", "gişe önü"),
    (r"peron (?:kenari|ucu|sonu|basi)", "peron kenarı"),
    (r"\bmezzanin\b|\bara kat\b", "mezzanin kat"),
    (r"\bust kat\b", "üst kat"),
    (r"\balt kat\b", "alt kat"),
    (r"\btunel agzi\b|\btunel girisi\b", "tünel ağzı"),
    (r"\bpersonel kapisi\b", "personel kapısı"),
    (r"\basansor onu\b", "asansör önü"),
    (r"\bkoridor\b", "koridor"),
    (r"\bperon\b", "peron"),
]

# LOCATION_PATTERNS gruplari normalize edilmis (aksansiz) metinden geldigi
# icin ciktida dogru Turkce yazimi geri getiren esleme.
LOCATION_KELIME_DUZELT = {
    "giris": "giriş", "cikis": "çıkış", "kapi": "kapı", "asansor": "asansör",
    "merdiven": "merdiven", "guney": "güney", "bati": "batı", "dogu": "doğu",
}


# Ekipman sozlugu. Uzun ifadeler once gelmeli (acgozlu eslesme): "peron kapısı"
# "kapı"dan once denenmeli, yoksa yanlis kisa eslesme olur.
EQUIPMENT = [
    # arac / tren
    "makinist kabini camı", "makinist kabini", "vagon kapısı", "vagon içi anons",
    "vagon aydınlatması", "fren sistemi", "fren", "klima", "tekerlek", "koltuk",
    "pantograf", "acil durdurma kolu",
    # istasyon mekanik
    "yürüyen merdiven", "asansör kapısı", "asansör kabini", "asansör",
    "peron kapısı", "psd", "turnike kolu", "turnike kapağı", "turnike",
    "bariyer", "otomatik giriş kapısı", "otomatik kapı",
    # elektrik
    "peron aydınlatması", "istasyon aydınlatması", "aydınlatma", "jeneratör",
    "ups", "elektrik panosu", "dağıtım panosu", "pano", "katener", "üçüncü ray",
    "trafo", "kablo", "sigorta",
    "acil durdurma butonu",
    # yazilim / bilet
    "bilet satış otomatı", "bilet otomatı", "biletmatik", "istanbulkart okuyucu",
    "istanbulkart", "pid ekranı", "pid ekranları", "pid", "sunucu", "veritabanı",
    "scada", "mobil uygulama", "hoparlör",
    # guvenlik
    "cctv", "kamera", "yangın söndürme tüpü", "yangın algılama", "yangın sensörü",
    "yangın dedektörü", "acil durum butonu", "acil çıkış", "kapı kilidi",
    # altyapi
    "tavan paneli", "tavan", "tünel duvarı", "duvar",
    "zemin", "fayans",
    "merdiven basamağı", "merdiven", "korkuluk", "drenaj", "kanalizasyon", "ray",
    "dilatasyon", "kapı kolu",
    # yolcu / temizlik
    "anons sistemi", "anons", "yolcu yönlendirme", "tuvalet", "çöp konteyneri",
    "çöp kutusu",
]

# Belirti sozlugu: (aranan_desen, kanonik_ad). Desen normalize edilmis metinde
# aranir (kucuk harf + aksansiz), bu yuzden desenler de aksansiz yazilmistir.
SYMPTOMS = [
    (r"calismiyor|calismiyo|calsmiyor", "çalışmıyor"),
    (r"acilmiyor|acilmiyo", "açılmıyor"),
    (r"kapanmiyor|kapatilmiyor", "kapanmıyor"),
    (r"kilitlenmiyor|kilitlemiyor", "kilitlenmiyor"),
    (r"\bdurdu\b|\bdurmus\b|\bdurduruldu\b|\bdurmis\b", "durdu"),
    (r"takil", "takılı"),
    (r"kirik|kirdi|kirildi|kirilmasi", "kırık"),
    (r"bozuk|bozuldu", "bozuk"),
    (r"ariza|arizali", "arıza"),
    (r"anormal ses|ses yapiyor|ses cikar|sesli", "anormal ses"),
    (r"titre", "titreşim"),
    (r"sizinti|sizma|damliyor|su birik", "sızıntı"),
    (r"catlak|catla", "çatlak"),
    (r"kesildi|kesinti", "kesinti"),
    (r"dondu|donmus", "dondu"),
    (r"hata veriyor|hata kodu|hatasi|hata", "hata"),
    (r"asiri isi|isinma|asiri sicaklik", "aşırı ısınma"),
    (r"basinc\w* dus|gerilim\w* dus|voltaj\w* dus|direnc\w* dusuk", "basınç/gerilim düşüşü"),
    (r"enerjisiz|enerji yok", "enerjisiz"),
    (r"\bsondu\b|\bsonuk\b|\byanmiyor\b|\bsonmus\b", "sönük"),
    (r"sigorta atma", "sigorta atması"),
    (r"kirli|kir birikimi|tozlu", "kirli"),
    (r"koku", "kötü koku"),
    (r"buzlanma|kaygan", "buzlanma/kayganlık"),
    (r"grafiti|grafit", "grafiti"),
    (r"cop|tasmis|tasti|doldu", "çöp birikmesi"),
    (r"dokul|dokunt|leke", "döküntü"),
    (r"supheli paket|supheli kutu|supheli esya", "şüpheli paket"),
    (r"yetkisiz|atlama|atladi", "yetkisiz giriş"),
    (r"kayip esya", "kayıp eşya"),
    (r"gecik", "sefer gecikmesi"),
    (r"iptal", "sefer iptali"),
    (r"seyrelt", "sefer seyreltme"),
    (r"personel eksik|personel yetmiyor", "personel eksikliği"),
    (r"yanlis anons|anons yapilmadi|anons yok", "anons sorunu"),
    (r"yogunluk|kalabalik", "yoğunluk"),
    (r"tuzlama", "tuzlama talebi"),
    (r"goruntu gelmiyor|goruntu yok|kor nokta|goruntusu bozul", "görüntü yok"),
    (r"\beksik\b|\beksigi\b", "eksik"),
    (r"dusme tehlikesi|duser tehlike|sarkit", "düşme tehlikesi"),
    (r"yirtik", "yırtık"),
    (r"yere dus|dustu", "yere düşmüş"),
    (r"kabul etmiyor|iade yapmiyor|vermiyor", "işlem yapmıyor"),
]


EQUIPMENT_ALIASES = {
    "trensformatör": "trafo",
    "transformatör": "trafo",
    "acil durdurma kutusu": "acil durdurma butonu",
    "acil durum butonu": "acil durum butonu",
    "tavan panel": "tavan paneli",
    "tavan sarkıtı": "tavan",
    "bariyer kapağı": "bariyer",
    "bariyer kolu": "bariyer",
    "yürüyen merdivan": "yürüyen merdiven",
    "biletmatik": "bilet satış otomatı",
    "bilet otomatı": "bilet satış otomatı",
    "istanbulkart yazılımı": "İstanbulkart okuyucu",
    "pid ekranları": "PID ekranı",
    "kamera sistemi": "kamera",
}


# ---------------------------------------------------------------------------
# Log veritabani + benzerlik / istatistik (Adim 8)
#
# Amac: kullanicinin yazdigi her cumleyi (ve mevcut egitim havuzunu) KAYIT
# ALTINA almak, ama otomatik olarak egitime SOKMAMAK. Bkz. CLAUDE.md
# "Loglama ve manuel onay" bolumu -- neden otomatik egitim yapilmadigi orada
# tartisiliyor (etiketsiz veri + confirmation bias riski).
# ---------------------------------------------------------------------------

# calisirken buyur, git'e girmez (.gitignore). NLP_LOG_DB ile Docker'da kalici bir volume'e
# yonlendirilebilir -- sensor tarafindaki RAYLI_KAYIT_DB deseniyle tutarli.
LOG_DB_FILE = Path(os.environ["NLP_LOG_DB"]) if os.environ.get("NLP_LOG_DB") else DATA_DIR / "logs.db"

# Benzerlik tespiti: modelin kendi pooler ciktisi (768 boyutlu) + cosine
# similarity. Ayri bir embedding modeli kurmuyoruz -- zaten yuklu olan
# BERTurk+LoRA'nin ic temsili siniflandirma icin egitildigi icin kategoriye
# gore kumelenmis olmasi beklenir.
#
# ESIK OLCULDU (20 Agu 2026, test setinden 150 kayit, 1334 ayni-kategori /
# 9841 farkli-kategori cift):
#   esik   ayni-kategori yakalanan   farkli-kategori YANLIS ALARM
#   0.50        %83.7                      %5.1
#   0.60        %76.0                      %2.4   <- SECILEN
#   0.65        %71.9                      %1.5
#   0.70        %67.1                      %0.9
#   0.80        %51.6                      %0.3
# Ilk tahmin 0.85'ti (SequenceMatcher esiklerinden esinlenerek), ama BERT
# pooler ciktisi farkli bir uzayda -- olcmeden tahmin etmek yanilticiydi:
# 0.85'te ayni-kategori kayitlarin coguKACIRILIRDI. 0.60 iyi bir denge:
# yuksek recall, dusuk yanlis alarm.
SIMILARITY_THRESHOLD = 0.60
SIMILARITY_MAX_SONUC = 30    # rapor kalabalik olmasin diye ust sinir
