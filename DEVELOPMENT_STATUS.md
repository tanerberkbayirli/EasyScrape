# Geliştirme durumu

0.2.0 sürümü, altı platformun bağlantılarını yalnızca kullanıcı tarafından seçilen indirme servislerine yönlendirir. YouTube, youtu.be ve Shorts bağlantıları `https://app.ytdown.to/tr37/` üzerinden işlenir. CLI tek URL, Tk arayüzü tek bağlantı alanı sunar. Ayarlar menüsünden kayıt klasörü ve global kısayol seçilir; varsayılanlar Masaüstü ve Ctrl+Shift+D'dir. Seçimler kalıcıdır; kısayol yeniden başlatmadan değiştirilir. Windows arayüzü arka planda hazır bekler ve her gösterildiğinde sağ alta konumlanır.

Çalışma zamanı bağımlılıkları Playwright ve HTTPX'tir. Edge/Chrome veya ayrıca kurulan Chromium kullanılır. Eski çıkarıcılar ve bunlara ait testler kaldırılmıştır.

Harici servislerin korumaları ve kullanılabilirliği canlı indirmeyi etkileyebilir. RedVid ve YTDown inceleme sırasında Cloudflare doğrulama ekranı döndürdü; Reddit/Pinterest/YouTube için gerçek video indirmesi doğrulanmış sayılmaz. Çevrimdışı tarayıcı entegrasyon testleri dış servislerin canlı çalıştığını kanıtlamaz.
