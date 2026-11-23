# EasyScrape İnceleme Raporu (16.10.2026)

## Nedir?
Python 3.10+ ile yazılmış bir komut satırı aracı (`easyscrape`, v0.1.0, MIT). Tek bir URL ya da URL listesi içeren bir .txt dosyasını alır, her URL'yi uygun "adapter"a yönlendirir ve medyayı indirir. İndirmeyi kendisi yapmaz; **yt-dlp** (video/ses) ve **gallery-dl** (görsel galerileri) üzerine ince bir katmandır. DRM/erişim kısıtı aşmaz, telemetri göndermez.

## Ne yapar?
- Platforma göre klasörleme (`youtube/`, `spotify/`, `pinterest/` ...), her öğe için `metadata.json`.
- Çıktı kökünde `report.txt`, `failed.json`, `.easyscrape-state.json` (tamamlananları atlar; `--force` ile yeniden indirir).
- Hata olan URL kaydedilir, kalanlar devam eder; yinelenen URL bir kez indirilir.
- Seçenekler: `--out`, `--audio-only`, `--limit-platform`, `--cookies`, `--cookies-from-browser`, `--no-metadata`, `--quiet`.
- Spotify: parça/albüm/oynatma listesi metadata'sı alınır, ardından YouTube Music'te başlık+sanatçı+süre (±2 sn) ile eşleştirilip ORADAN ses indirilir (Spotify'ın kendi akışı değil); etiketler (mutagen) yazılır.
- İndirilen videoda ffprobe ile video akışı doğrulanır (sadece ses inmişse hata verir).
- Windows'ta Deno/Node/Bun/QuickJS'i otomatik bulup yt-dlp'ye verir (YouTube imza çözümü için).

## Kod sağlığı
- pytest: 214 geçti, 19 atlandı (çoğu symlink/Linux'a özgü). ruff ve mypy (strict): temiz.
- Not: çalışma ağacında commit edilmemiş değişiklikler var (cli.py, yt_dlp_adapter.py, test_links.txt, tests/conftest.py, video_check/).

## Canlı indirme testi (bu makinede, cookie'siz)
| İçerik | Sonuç |
|---|---|
| YouTube video (Me at the zoo) | ✅ webm indi |
| YouTube 4K (Rick Astley, AV1 2160p + Opus; ffprobe ile doğrulandı) | ✅ |
| YouTube 4K uzun video (Big Buck Bunny, 722 MB) | ✅ |
| YouTube `--audio-only` | ✅ |
| Spotify parça | ✅ .opus (YouTube Music eşleşmesiyle) |
| Pinterest pin (görsel) | ✅ .jpg |
| Genel yt-dlp sitesi: Wikimedia Commons video (2.9 GB) | ✅ |
| Genel: archive.org video | ✅ .avi |
| SoundCloud — `--audio-only` ile | ✅ .m4a |
| SoundCloud — normal modda | ❌ "video akışı yok" (tasarım gereği; `--audio-only` gerekir) |
| Instagram, Facebook, Threads | ❌ giriş (cookie) gerekli – uygulama net hata mesajı veriyor. Threads için ayrıca hiçbir extractor yok, cookie ile de inmez. |
| Vimeo | ❌ yt-dlp giriş istiyor ("web client only works when logged in") |
| Dailymotion | ❌ "Access forbidden" |
| TikTok | ❌ "Unexpected response" (impersonation hedefi yok; curl_cffi kurulumu gerekebilir) |
| Reddit | ❌ "blocked by network security" (anonim istek engelleniyor; test URL'si de gerçek bir gönderi değildi) |
| X/Twitter | ⚠️ Doğrulanamadı: test ettiğim tweet ID'leri gerçek değildi; gallery-dl `KeyError 'result'` verdi (genelde giriş gerektirir) |
| Bilibili | ❌ bölge/giriş kısıtı |
| Sertifikası bozuk site (sample-videos.com) | ❌ SSL hatası (sitenin kusuru) |

Test dışı kalan: Instagram/Facebook cookie'li çalışması (hesap bilgisi kullanmadım), YouTube oynatma listeleri, Spotify albüm/playlist, gerçek X/Reddit gönderileri.

## Yapamadıkları / sınırlar
1. Giriş gerektiren her şey (Instagram, Facebook, Threads, çoğu zaman X/Vimeo) cookie olmadan inmez.
2. Threads'te hiçbir desteği yok (README de belirtiyor).
3. DRM'li veya özel içerik; Spotify'ın kendi ses akışı/FLAC.
4. Spotify eşleşmesi kesin değil: YouTube Music'te ±2 sn süreyle eşleşme bulunamazsa parça inmez; kalite kaynağa bağlı (~256 kbps üstü yok), albüm adı bazen "Unknown album" kalıyor.
5. Her şey upstream yt-dlp/gallery-dl'ye bağlı; siteler değişince kırılır. TikTok gibi sitelerde ek bağımlılık gerekir.
6. Yalnızca-ses kaynaklar (SoundCloud) `--audio-only` istiyor; normal modda "başarısız" sayılıyor, otomatik geri düşme yok.

## Küçük öneriler
- Ses-sadece kaynaklarda otomatik audio moduna düşme.
- TikTok için `curl_cffi` (impersonation) bağımlılığını dokümante et/ekle.
- Spotify çıktısında albüm adı eksikliği ("Unknown album") iyileştirilebilir.

---

# Geliştirme Raporu (16.10.2026, ikinci tur)

## Yapılan geliştirmeler
| # | Geliştirme | Dosya |
|---|---|---|
| 1 | **Spotify albüm ve playlist artık iniyor.** Önceki kod, Spotify'ın embed sayfası parça sayısını bildirmediği için her koleksiyonu reddediyordu. Sayı artık ana sayfadan okunuyor; eksik/sınırlı koleksiyon (embed en fazla 100 parça verir) hata yerine uyarıyla indiriliyor. | spotify_metadata.py, spotify_adapter.py |
| 2 | **Remaster/yeniden basım eşleşmesi.** Albüm testinde 10 parçanın 6'sı "±2 sn" kuralı yüzünden bulunamıyordu. Şimdi önce sıkı eşleşme, bulunamazsa başlığı birebir aynı olan ve sanatçısı doğrulanan sonuç max(10 sn, %5) toleransla kabul ediliyor ve "yaklaşık eşleşme" uyarısı düşülüyor. "(2023 Remaster)" gibi ekler başlık karşılaştırmasında yok sayılıyor. Albüm: 4/10 → 10/10. | spotify_matching.py |
| 3 | Playlist parçalarında "Unknown album" sorunu giderildi (albüm adı parça sayfasından okunuyor). | spotify_metadata.py |
| 4 | Spotify indirmesinde geçici YouTube 403 hatası artık yeniden deneniyor. | spotify_adapter.py |
| 5 | **Instagram reel'leri cookie'siz** önce deneniyor (önceki turda). | social.py |
| 6 | **TikTok** için `curl-cffi` bağımlılığı eklendi. | pyproject.toml |
| 7 | **Çoklu kaynak:** `easyscrape a.txt b.txt https://...`; metin dosyalarında satır içindeki tüm linkler yakalanıyor (not/yorum içeren satırlar sorun değil). | input.py, cli.py |
| 8 | **Başarısızları yeniden dene:** `easyscrape failed.json`. | input.py |
| 9 | Yeni seçenekler: `--max-items N`, `--max-height PX`, `--audio-format mp3\|m4a\|opus\|flac\|wav`; ek tarayıcılar (brave, opera, vivaldi, chromium, safari) cookie için. | cli.py, models.py, yt_dlp_adapter.py, gallery_dl_adapter.py |
| 10 | Yalnızca-ses kaynaklar (SoundCloud) artık `--audio-only` gerektirmeden ses olarak iniyor, nota düşülüyor. | yt_dlp_adapter.py |
| 11 | Genel yedek: yt-dlp başarısız olursa gallery-dl'nin desteklediği her site (Imgur, Tumblr, Bluesky, RedGifs...) deneniyor. | generic.py |
| 12 | Reddit engel hatasında cookie yönlendirmesi. | social.py |
| 13 | README güncellendi. | README.md |

## Canlı test sonuçları (bu makinede)
| Test | Sonuç |
|---|---|
| Spotify albüm (Dark Side of the Moon, 10 parça) | ✅ 10/10 (6'sı "yaklaşık eşleşme" uyarısıyla) |
| Spotify playlist (130 parçalık, `--max-items 2`) | ✅; uyarı: embed sadece 100 parça gösteriyor |
| Spotify albüm (OK Computer) | ✅ albüm adı doğru klasörde |
| Karma toplu liste (prozlu .txt: YouTube, Spotify, SoundCloud, X, Instagram, TikTok, Pinterest) | ✅ 7/7 geçerli link |
| X video (3 gönderi) | ✅ |
| Instagram reel (3/4; biri 18+ kısıtlı) | ✅ / ❌ cookie gerekir |
| TikTok video | ✅ 3/4 (4.sü slayt gösterisi) |
| Pinterest video pin | ✅ mp4 |
| `--audio-format mp3` (YouTube + SoundCloud) | ✅ |
| `failed.json` ile yeniden deneme | ✅ |
| pytest | 225 geçti, 19 atlandı; ruff ve mypy temiz |

## Hâlâ yapamadıkları
1. **Reddit:** bu ağda anonim erişim tamamen engelli; cookie ile denenmedi.
2. **18+ / özel / giriş gerektiren** Instagram, Facebook, Threads içerikleri; Threads için hiçbir extractor yok.
3. **TikTok fotoğraf slaytları** (video akışı yok).
4. **100'den uzun Spotify playlist'lerinin** 100. parçadan sonrası (Spotify giriş olmadan vermiyor). Uyarı veriliyor.
5. Vimeo, Dailymotion, Bilibili gibi sitelerde giriş/bölge kısıtı.
6. Spotify'ın kendi ses akışı değil, YouTube Music eşleşmesi iner; kalite ~256 kbps ile sınırlı, bazı parçalar eşleşemeyebilir.
7. İndirmeler hâlâ sırayla yapılıyor (paralel indirme eklenmedi; paylaşılan durum nedeniyle riskli).
