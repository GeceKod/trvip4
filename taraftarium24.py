import re
import sys
import time
import urllib.request
from urllib.parse import urlparse, parse_qs, urljoin
from playwright.sync_api import sync_playwright

# Taraftarium ana domain'i
TARAFTARIUM_DOMAIN = "https://taraftarium24.xyz/"

# Kullanılacak User-Agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def check_url_exists(url):
    """
    Verilen URL'nin çalışıp çalışmadığını (200 OK) kontrol eder (HEAD isteği).
    """
    try:
        req = urllib.request.Request(
            url, 
            method='HEAD', 
            headers={'User-Agent': USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except:
        return False

def scrape_default_channel_info(page):
    print(f"\n📡 Varsayılan kanal bilgisi {TARAFTARIUM_DOMAIN} adresinden alınıyor...")
    try:
        page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
        time.sleep(3)

        iframe_selector = "iframe#customIframe"
        try:
            page.wait_for_selector(iframe_selector, timeout=10000)
        except:
            print("⚠️ Iframe hemen bulunamadı, devam ediliyor...")

        iframe_element = page.query_selector(iframe_selector)

        if not iframe_element:
            print("❌ Ana sayfada 'iframe#customIframe' bulunamadı.")
            return None, None

        iframe_src = iframe_element.get_attribute('src')
        if not iframe_src:
            return None, None

        event_url = urljoin(TARAFTARIUM_DOMAIN, iframe_src)
        parsed_event_url = urlparse(event_url)
        query_params = parse_qs(parsed_event_url.query)
        stream_id = query_params.get('id', [None])[0]

        print(f"✅ Varsayılan kanal bilgisi alındı: ID='{stream_id}'")
        return event_url, stream_id

    except Exception as e:
        print(f"❌ Varsayılan kanal hatası: {e}")
        return None, None

def extract_base_m3u8_url(page, event_url):
    try:
        print(f"\n-> Base URL için Event sayfasına gidiliyor: {event_url}")
        page.goto(event_url, timeout=20000, wait_until="domcontentloaded")
        content = page.content()
        
        base_url_match = re.search(r"['\"](https?://[^'\"]+/checklist/)['\"]", content)
        if not base_url_match:
             base_url_match = re.search(r"streamUrl\s*=\s*['\"](https?://[^'\"]+/checklist/)['\"]", content)
        
        if base_url_match:
            base_url = base_url_match.group(1)
            print(f"-> ✅ M3U8 Base URL bulundu: {base_url}")
            return base_url
            
    except Exception as e:
        print(f"-> ❌ Base URL hatası: {e}")
    
    fallback = "https://andro.1386503.xyz/checklist/"
    print(f"-> ⚠️ Base URL bulunamadı, yedek kullanılıyor: {fallback}")
    return fallback

def scrape_all_channels(page, base_m3u8_url):
    """
    Hem maç listesini hem de menüdeki linkleri tarar.
    """
    print(f"\n📡 Tüm kanallar {TARAFTARIUM_DOMAIN} adresinden geniş kapsamlı taranıyor...")
    channels = []
    seen_ids = set() # Çifte kayıtları önlemek için ID takibi

    try:
        if page.url != TARAFTARIUM_DOMAIN:
            page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
        
        # --- YÖNTEM 1: MAÇ LİSTESİNDEKİ KANALLAR (.mac sınıfı) ---
        print("-> 1. Aşama: Maç listesi taranıyor...")
        mac_elements = page.query_selector_all(".mac[data-url]")
        
        raw_channels_data = []

        for el in mac_elements:
            try:
                name_el = el.query_selector(".takimlar")
                name = name_el.inner_text().strip() if name_el else "İsimsiz Maç"
                data_url = el.get_attribute('data-url')
                if data_url:
                     raw_channels_data.append({"name": name, "url": data_url})
            except: continue

        # --- YÖNTEM 2: MENÜDEKİ VE DİĞER LİNKLER (ATV, A Spor vb.) ---
        print("-> 2. Aşama: Menü ve genel linkler taranıyor...")
        # İçinde 'channel.html?id=' geçen tüm linkleri bul
        link_elements = page.query_selector_all("a[href*='channel.html?id=']")
        
        for el in link_elements:
            try:
                href = el.get_attribute('href')
                name = el.inner_text().strip()
                # İsmi çok uzunsa veya boşsa atla
                if not name or len(name) > 50: continue
                # Gereksiz boşlukları temizle
                name = re.sub(r'\s+', ' ', name)
                
                if href:
                    raw_channels_data.append({"name": name, "url": href})
            except: continue

        print(f"-> Toplam {len(raw_channels_data)} adet potansiyel kanal bulundu. İşleniyor...")

        # --- ORTAK İŞLEME VE DÜZELTME DÖNGÜSÜ ---
        for item in raw_channels_data:
            url_str = item['url']
            raw_name = item['name']
            
            # URL'den ID'yi çıkar
            stream_id = None
            try:
                if '?' in url_str:
                    # Tam URL ise parse et, değilse manuel split yap
                    if url_str.startswith('http') or url_str.startswith('/'):
                        # Urljoin ile tamir et ki urlparse çalışsın
                        full_temp_url = urljoin(TARAFTARIUM_DOMAIN, url_str)
                        parsed = urlparse(full_temp_url)
                        stream_id = parse_qs(parsed.query).get('id', [None])[0]
            except: pass

            if stream_id:
                # --- AKILLI DÜZELTME VE KONTROL ---
                
                # 1. BeIN Sports 1 (Receptestt Kontrolü)
                if stream_id == "androstreamlivebs1" or stream_id == "facebooklivebs1":
                    test_url = f"{base_m3u8_url}receptestt.m3u8"
                    # Bu kontrolü her döngüde yapmamak için cache mantığı eklenebilir ama
                    # set() kullandığımız için zaten sadece bir kez buraya girecek.
                    if "receptestt.m3u8" not in seen_ids and "androstreamlivebs1.m3u8" not in seen_ids:
                        print(f"   ❓ BeIN 1 bulundu. Sunucu kontrolü yapılıyor...", end=" ")
                        if check_url_exists(test_url):
                            print("✅ 'receptestt' AKTİF")
                            final_filename = "receptestt.m3u8"
                        else:
                            print("❌ 'receptestt' PASİF (Orijinal ID kullanılıyor)")
                            final_filename = "androstreamlivebs1.m3u8"
                    else:
                        # Zaten işlendiyse atla
                        continue

                # 2. Max Kanalları (max -> bsm)
                elif "androstreamlivemax" in stream_id:
                    final_id = stream_id.replace("max", "bsm")
                    final_filename = f"{final_id}.m3u8"
                
                # 3. Diğerleri (ATV, A Spor, TV8 vb. buraya düşecek)
                else:
                    final_filename = f"{stream_id}.m3u8"

                # Listeye Ekle (Benzersizlik Kontrolü)
                if final_filename not in seen_ids:
                    # İsimdeki "CANLI" vb. kelimeleri temizle
                    clean_name = raw_name.replace('CANLI', '').strip()
                    
                    channels.append({
                        'name': clean_name,
                        'filename': final_filename
                    })
                    seen_ids.add(final_filename)

        print(f"✅ {len(channels)} adet benzersiz kanal başarıyla listelendi.")
        return channels

    except Exception as e:
        print(f"❌ Kanal tarama hatası: {e}")
        return []

def get_channel_group(channel_name):
    n = channel_name.lower()
    if "bein" in n: return "BeinSports"
    if "s sport" in n or "ssport" in n: return "S Sports"
    if "tivibu" in n: return "Tivibu"
    if "exxen" in n: return "Exxen"
    if "smart" in n: return "Smart Spor"
    if "nba" in n: return "NBA"
    if "trt" in n: return "TRT"
    if any(x in n for x in ["atv", "a spor", "tv8", "kanald", "show", "startv", "foxtv", "nowtv", "tv 8"]): return "Ulusal Kanallar"
    if "euro" in n: return "EuroSport"
    return "Diğer"

def main():
    with sync_playwright() as p:
        print("🚀 Playwright ile Taraftarium24 Full Botu Başlatılıyor...")

        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--autoplay-policy=no-user-gesture-required'
        ]

        browser = p.chromium.launch(headless=True, args=browser_args)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # 1. Base URL Bul
        default_event_url, _ = scrape_default_channel_info(page)
        
        if default_event_url:
            base_m3u8_url = extract_base_m3u8_url(page, default_event_url)
        else:
            base_m3u8_url = "https://andro.1386503.xyz/checklist/"
            print(f"⚠️ Manuel Base URL: {base_m3u8_url}")

        # 2. Tüm kanalları (Liste + Menü) tara
        channels = scrape_all_channels(page, base_m3u8_url)

        if not channels:
            print("❌ Hiçbir kanal bulunamadı!")
            browser.close()
            sys.exit(1)

        # 3. Dosyayı Yaz
        output_filename = "kanallar4.m3u8"
        m3u_content = []
        
        m3u_content.append("#EXTM3U")
        m3u_content.append(f"#EXT-X-USER-AGENT:{USER_AGENT}")
        m3u_content.append(f"#EXT-X-REFERER:{TARAFTARIUM_DOMAIN}")
        m3u_content.append(f"#EXT-X-ORIGIN:{TARAFTARIUM_DOMAIN.rstrip('/')}")

        print(f"\n📺 {len(channels)} kanal linki oluşturuluyor...")

        for ch in channels:
            full_link = f"{base_m3u8_url}{ch['filename']}"
            group = get_channel_group(ch['name'])
            m3u_content.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}",{ch["name"]}')
            m3u_content.append(full_link)

        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(m3u_content))

        print(f"\n📂 Dosya kaydedildi: {output_filename}")
        browser.close()
        print("\n🎉 İşlem tamamlandı!")

if __name__ == "__main__":
    main()
