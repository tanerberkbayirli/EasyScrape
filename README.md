# EasyScrape

Bir video bağlantısı yapıştırın; EasyScrape platformu tanır, ilgili indirme servisine gönderir ve MP4 videoyu seçtiğiniz klasöre kaydeder. Varsayılan kayıt yeri Masaüstüdür.

- X / Twitter → https://ssstwitter.com/
- TikTok (vm/vt kısa linkleri dahil) → https://ssstik.io/
- Instagram → https://reelsvideo.io/en-4
- Reddit (redd.it kısa linkleri dahil) → https://redvid.io/
- Pinterest (pin.it kısa linkleri dahil) → https://redvid.io/pinterest-downloader

Yalnızca bu beş platform ve video indirme desteklenir. Eski yt-dlp/gallery-dl adaptörleri, YouTube, Spotify, fotoğraf, ses dönüştürme, dosyadan/toplu indirme, kalite seçenekleri, çerez seçimi, rapor ve geçmiş özellikleri kaldırılmıştır.

## Kurulum ve kullanım

Python 3.10+ ve Microsoft Edge veya Google Chrome gerekir.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install .
.venv\Scripts\easyscrape-gui.exe
```

Edge/Chrome yoksa bir kez Chromium kurun:

```powershell
.venv\Scripts\python.exe -m playwright install chromium
```

Arayüzde bağlantıyı yapıştırıp **İndir** düğmesine veya Enter'a basın.

**Ayarlar** düğmesinden kayıt klasörünü ve uygulamayı açma kısayolunu seçebilirsiniz. Varsayılanlar **Masaüstü** ve **Ctrl + Shift + D**'dir. **Kaydet** ile seçimler hemen uygulanır ve yeniden açılışlarda korunur. Kullanımda olan bir kısayol seçilirse önceki kısayol korunur. **Varsayılanlara dön** düğmesi alanları ilk değerlere getirir; uygulamak için Kaydet'e basın. Ayarlar Windows'ta `%APPDATA%\EasyScrape\settings.json` dosyasında saklanır. Komut satırı da kayıt klasörü ayarını kullanır.

Windows'ta uygulama seçilen kısayolu doğrudan dinler. Pencereyi kapatmak uygulamayı arka planda hazır tutar; aynı tuş veya kısayol mevcut pencereyi yeniden gösterir. Tamamen kapatmak için pencereye sağ tıklayıp **Tamamen çık** seçin. İndirme kütüphaneleri yalnızca indirme başlatıldığında yüklenir.

Windows başlangıcında gizli çalıştırmak için kısayol hedefinde `pythonw.exe -m easyscrape.gui --background` kullanılabilir. Bu bilgisayarda Başlangıç klasörüne bu kısayol eklendi. Ctrl + Shift + D, uygulamanın kendi tuş dinleyicisi tarafından yönetildiğinden Windows kısayolunun “Kısayol tuşu” alanı boş bırakılır.

```powershell
.venv\Scripts\easyscrape.exe "https://x.com/kullanici/status/123456789"
```

İndirme sırasında ayrı bir tarayıcı penceresi açılır. Bağlantı otomatik doldurulup gönderilir; sonuçtaki video bağlantıları işlenir. Servis CAPTCHA/insan doğrulaması isterse açılan tarayıcıda kendiniz tamamlayın. Formun kullanılabilir olması ve sonucun hazırlanması için ayrı ayrı en fazla üç dakika beklenir. Tarayıcıyı kapatmak işlemi durdurur. Koruma mekanizmaları aşılmaz.

Video içeren MP4 dosyası doğrulandıktan sonra seçilen kayıt klasörüne `x_20261102_213000.mp4` gibi bir adla yazılır. Aynı adlı dosyalar ezilmez. Windows'ta OneDrive veya başka bir konuma yönlendirilmiş Masaüstü, sistem ayarından okunur. Geçici indirmeler temizlenir; kayıt klasörüne rapor veya metadata bırakılmaz.

İşlem sitelerin kullanılabilirliğine, herkese açık içeriği çözebilmesine ve sayfa yapısına bağlıdır. Özel hesaplar, silinmiş içerikler ve fotoğraf gönderileri video olarak indirilemez. Servisler değişirse form/sonuç seçicilerinin güncellenmesi gerekebilir. Video adresi seçilen üçüncü taraf servise gönderilir; medya o servisin sunduğu indirme bağlantısından alınır.

## Geliştirme

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m mypy src/easyscrape
.venv\Scripts\python.exe -m build
```

Testler dış servislerden video indirmez. Platform eşleştirmesi, geçersiz adresler, MP4/video kontrolü, dosya çakışmaları ve tarayıcı formundan yerel test sunucusuna indirme akışı sınanır.
