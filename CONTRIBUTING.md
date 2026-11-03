# Katkı rehberi

Kurulum ve kontroller için README.md dosyasına bakın.

Platform-servis eşleştirmesi ve tarayıcı indirme akışı `src/easyscrape/downloader.py` içindedir. Kapsam YouTube, X, TikTok, Instagram, Reddit ve Pinterest videolarıdır. YouTube için yalnızca `https://app.ytdown.to/tr37/` kullanılır. Yeni bir genel çıkarıcı veya alternatif indirme sağlayıcısı eklemeyin.

Servis formu veya indirme bağlantıları değiştiğinde yerel HTML örnekleriyle tarayıcı testlerini güncelleyin. Testler gerçek üçüncü taraf servislerine, hesaplara veya indirilen kişisel medyaya bağımlı olmamalıdır. Başarısız ve kısmi dosyalar Masaüstüne teslim edilmemeli; mevcut dosyalar ezilmemelidir.

CAPTCHA ve diğer erişim korumalarını aşan kod eklemeyin. Doğrulama kullanıcının açılan tarayıcıda tamamlayabileceği şekilde kalmalıdır.
