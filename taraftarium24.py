import re
import sys
import time
from urllib.parse import urlparse, parse_qs, urljoin
from playwright.sync_api import sync_playwright, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError

# Taraftarium ana domain'i
TARAFTARIUM_DOMAIN = "https://taraftarium24.xyz/"

# Kullanılacak User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.0 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# --- Varsayılan Kanal Bilgisini Alma Fonksiyonu (DEĞİŞİKLİK YOK) ---
def scrape_default_channel_info(page):
    print(f"\n📡 Varsayılan kanal bilgisi {TARAFTARIUM_DOMAIN} adresinden alınıyor...")
    try:
        # Ana sayfaya ilk gidiş. DOM'un yüklenmesini bekle.
        page.goto(TARAFTARIUM_DOMAIN, timeout=25000, wait_until='domcontentloaded')

        iframe_selector = "iframe#customIframe"
        print(f"-> Varsayılan iframe ('{iframe_selector}') aranıyor...")
        page.wait_for_selector(iframe_selector, timeout=15000) # Biraz daha bekle
        iframe_element = page.query_selector(iframe_selector)

        if not iframe_element:
            print("❌ Ana sayfada 'iframe#customIframe' bulunamadı.")
            return None, None

        iframe_src = iframe_element.get_attribute('src')
        if not iframe_src:
            print("❌ Iframe 'src' özniteliği boş.")
            return None, None

        event_url = urljoin(TARAFTARIUM_DOMAIN, iframe_src)
        parsed_event_url = urlparse(event_url)
        query_params = parse_qs(parsed_event_url.query)
        stream_id = query_params.get('id', [None])[0]

        if not stream_id:
            print(f"❌ Event URL'sinde ({event_url}) 'id' parametresi bulunamadı.")
            return None, None

        print(f"✅ Varsayılan kanal bilgisi alındı: ID='{stream_id}', EventURL='{event_url}'")
        return event_url, stream_id

    except Exception as e:
        print(f"❌ Ana sayfaya ulaşılamadı veya iframe bilgisi alınamadı: {e.__class__.__name__} - {e}")
        return None, None

# --- M3U8 Base URL Çıkarma Fonksiyonu (DEĞİŞİKLİK YOK) ---
def extract_base_m3u8_url(page, event_url):
    try:
        print(f"\n-> M3U8 Base URL'i almak için Event sayfasına gidiliyor: {event_url}")
        page.goto(event_url, timeout=20000, wait_until="domcontentloaded")
        content = page.content()
        base_url_match = re.search(r"['\"](https?://[^'\"]+/checklist/)['\"]", content)
        if not base_url_match:
             base_url_match = re.search(r"streamUrl\s*=\s*['\"](https?://[^'\"]+/checklist/)['\"]", content)
        if not base_url_match:
            print(" -> ❌ Event sayfası kaynağında '/checklist/' ile biten base URL bulunamadı.")
            return None
        base_url = base_url_match.group(1)
        print(f"-> ✅ M3U8 Base URL bulundu: {base_url}")
        return base_url
    except Exception as e:
        print(f"-> ❌ Event sayfası işlenirken hata oluştu: {e}")
        return None

# --- GÜNCELLENEN FONKSİYON: 'networkidle' yerine 'wait_for_selector' kullanıldı ---
def scrape_all_channels(page):
    """
    Taraftarium ana sayfasında JS'in yüklenmesini bekler ve TÜM kanalların
    isimlerini ve ID'lerini (yinelenenler dahil) kazır.
    """
    print(f"\n📡 Tüm kanallar {TARAFTARIUM_DOMAIN} adresinden çekiliyor...")
    channels = [] # Sonuç listesi
    try:
        mac_item_selector = ".mac[data-url]"

        print(f"-> Ana sayfaya ({TARAFTARIUM_DOMAIN}) gidiliyor...")
        # 'networkidle' yerine 'domcontentloaded' kullanıyoruz (daha hızlı).
        page.goto(TARAFTARIUM_DOMAIN, timeout=45000, wait_until='domcontentloaded')
        print("-> Sayfa DOM'u yüklendi.")

        # Kritik değişiklik: 'networkidle' veya 5 saniyelik kör 'timeout' beklemek yerine,
        # ihtiyacımız olan asıl kanal elementlerinin (JS ile) yüklenmesini bekliyoruz.
        print(f"-> Kanal listesinin ('{mac_item_selector}') yüklenmesi bekleniyor (Max 30sn)...")
        page.wait_for_selector(mac_item_selector, timeout=30000)
        print("-> ✅ Kanal listesi DOM'da bulundu.")

        # 'wait_for_selector' başarılı olduğu için 'elements_exist' kontrolüne gerek yok.
        
        print("-> Bilgiler çıkarılıyor...")
        channel_elements = page.query_selector_all(mac_item_selector)
        print(f"-> {len(channel_elements)} adet potansiyel kanal elemanı bulundu.")

        # --- DEĞİŞİKLİK: processed_ids ve filtreleme kaldırıldı (Mevcut kodunuzda da böyleydi) ---
        for element in channel_elements:
            name_element = element.query_selector(".takimlar")
            channel_name = name_element.inner_text().strip() if name_element else "İsimsiz Kanal"
            channel_name_clean = channel_name.replace('CANLI', '').strip()

            data_url = element.get_attribute('data-url')
            stream_id = None
            if data_url:
                try:
                    parsed_data_url = urlparse(data_url)
                    query_params = parse_qs(parsed_data_url.query)
                    stream_id = query_params.get('id', [None])[0]
                except Exception:
                    pass

            if stream_id: # Sadece ID varsa ekle
                time_element = element.query_selector(".saat")
                time_str = time_element.inner_text().strip() if time_element else None
                if time_str and time_str != "CANLI":
                     final_channel_name = f"{channel_name_clean} ({time_str})"
                else:
                     final_channel_name = channel_name_clean

                # Direkt listeye ekle, ID kontrolü yok
                channels.append({
                    'name': final_channel_name,
                    'id': stream_id
                })
        # --- DEĞİŞİKLİK BİTTİ ---

        # Kanalları isme göre sırala (isteğe bağlı)
        channels.sort(key=lambda x: x['name'])

        print(f"✅ {len(channels)} adet kanal bilgisi başarıyla çıkarıldı (yinelenenler dahil).")
        return channels

    except Exception as e:
        if "timeout" in str(e).lower() and mac_item_selector in str(e):
             print(f"❌ Kanal listesi yüklenemedi (Timeout): '{mac_item_selector}' elementi 30sn içinde bulunamadı.")
        else:
             print(f"❌ Kanal listesi işlenirken hata oluştu: {e}")
        return []

# --- Gruplama Fonksiyonu (Güncellendi: Daha fazla anahtar kelime) ---
def get_channel_group(channel_name):
    channel_name_lower = channel_name.lower()
    group_mappings = {
        'BeinSports': ['bein sports', 'beın sports', ' bs', ' bein '],
        'S Sports': ['s sport'],
        'Tivibu': ['tivibu spor', 'tivibu'],
        'Exxen': ['exxen'],
        'Ulusal Kanallar': ['a spor', 'trt spor', 'trt 1', 'tv8', 'atv', 'kanal d', 'show tv', 'star tv', 'trt yıldız', 'a2'],
        'Spor': ['smart spor', 'nba tv', 'eurosport', 'sport tv', 'premier sports', 'ht spor', 'sports tv'],
        'Yarış': ['tjk tv'],
        'Belgesel': ['national geographic', 'nat geo', 'discovery', 'dmax', 'bbc earth', 'history'],
        'Film & Dizi': ['bein series', 'bein movies', 'movie smart', 'filmbox', 'sinema tv'],
        'Haber': ['haber', 'cnn', 'ntv'],
        'Diğer': ['gs tv', 'fb tv', 'cbc sport'] # Eşleşmeyenler ve kulüp kanalları
    }
    for group, keywords in group_mappings.items():
        for keyword in keywords:
            if keyword in channel_name_lower:
                return group

    # Maç isimlerini ayıklama (Lig bilgisine göre daha iyi olabilir ama şimdilik basit)
    if re.search(r'\d{2}:\d{2}', channel_name): # İçinde saat varsa maçtır
        return "Maç Yayınları"
    if ' - ' in channel_name: # Takım ismi gibi görünüyorsa
        return "Maç Yayınları"

    return "Diğer Kanallar" # Kalanlar için varsayılan

# --- Ana Fonksiyon ---
def main():
    with sync_playwright() as p:
        print("🚀 Playwright ile Taraftarium24 M3U8 Kanal İndirici Başlatılıyor (Tüm Liste)...")

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # 1. Adım: Varsayılan kanaldan event URL'sini ve ID'sini al
        default_event_url, default_stream_id = scrape_default_channel_info(page)
        if not default_event_url:
            print("❌ UYARI: Varsayılan kanal bilgisi alınamadı, M3U8 Base URL bulunamıyor. İşlem sonlandırılıyor.")
            browser.close()
            sys.exit(1)

        # 2. Adım: event.html'den M3U8 Base URL'ini çıkar
        base_m3u8_url = extract_base_m3u8_url(page, default_event_url)
        if not base_m3u8_url:
            print("❌ UYARI: M3U8 Base URL alınamadı. İşlem sonlandırılıyor.")
            browser.close()
            sys.exit(1)

        # 3. Adım: Ana sayfadaki tüm kanalları kazı
        channels = scrape_all_channels(page)
        if not channels:
            print("❌ UYARI: Hiçbir kanal bulunamadı, işlem sonlandırılıyor.")
            browser.close()
            sys.exit(1)

        m3u_content = []
        # KRİTİK DEĞİŞİKLİK: Çıktı dosya adını kanallar4.m3u8 olarak değiştir.
        output_filename = "kanallar4.m3u8"
        print(f"\n📺 {len(channels)} kanal için M3U8 linkleri oluşturuluyor...")
        created = 0

        player_origin_host = TARAFTARIUM_DOMAIN.rstrip('/')
        player_referer = TARAFTARIUM_DOMAIN

        m3u_header_lines = [
            "#EXTM3U",
            f"#EXT-X-USER-AGENT:{USER_AGENT}",
            f"#EXT-X-REFERER:{player_referer}",
            f"#EXT-X-ORIGIN:{player_origin_host}"
        ]

        for i, channel_info in enumerate(channels, 1):
            channel_name = channel_info['name']
            stream_id = channel_info['id']
            # Gruplamayı ID'ye göre değil, isme göre yapalım
            group_name = get_channel_group(channel_name)

            m3u8_link = f"{base_m3u8_url}{stream_id}.m3u8"

            m3u_content.append(f'#EXTINF:-1 tvg-name="{channel_name}" group-title="{group_name}",{channel_name}')
            m3u_content.append(m3u8_link)
            created += 1

        browser.close()

        if created > 0:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write("\n".join(m3u_header_lines))
                f.write("\n")
                f.write("\n".join(m3u_content))
            print(f"\n\n📂 {created} kanal başarıyla '{output_filename}' dosyasına kaydedildi.")
        else:
            print("\n\nℹ️  Geçerli hiçbir M3U8 linki oluşturulamadığı için dosya oluşturulmadı.")

        print("\n🎉 İşlem tamamlandı!")

if __name__ == "__main__":
    main()
