# Geliştirme durumu

1.0.0 sürümü, on platform/video türünün (YouTube, YouTube Shorts, X, TikTok, Instagram, Instagram Reels, Reddit, Snapchat Spotlight, Pinterest, Threads) bağlantılarını canlı çalışması doğrulanmış indirme servislerine yönlendirir:

- YouTube & YouTube Shorts → `https://vidssave.com/`
- X / Twitter → `https://ssstwitter.com/`
- TikTok → `https://ssstik.io/`
- Instagram & Instagram Reels → `https://fastdl.app/en`
- Reddit → `https://viddit.io/`
- Snapchat Spotlight → `https://getindevice.com/snapchat-downloader/`
- Pinterest → `https://pindown.io/`
- Threads → `https://threadster.app/`

CLI tek URL, Tk arayüzü tek bağlantı alanı sunar. Ayarlar menüsünden kayıt klasörü ve global kısayol seçilir; varsayılanlar Masaüstü ve Ctrl+Shift+D'dir. Seçimler kalıcıdır; kısayol yeniden başlatmadan değiştirilir. Windows arayüzü arka planda hazır bekler ve her gösterildiğinde sağ alta konumlanır.

Çalışma zamanı bağımlılıkları Playwright ve HTTPX'tir. Edge/Chrome veya ayrıca kurulan Chromium kullanılır. Eski çıkarıcılar ve bunlara ait testler kaldırılmıştır.
