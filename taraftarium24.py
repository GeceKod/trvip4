import re
import sys
import time
import urllib.request
from urllib.parse import urlparse, parse_qs, urljoin
from playwright.sync_api import sync_playwright

# Taraftarium ana domain'i
TARAFTARIUM_DOMAIN = "https://taraftarium24.xyz/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/5.0 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def check_url_exists(url):
    """URL kontrolü (BeIN 1 için)"""
    try:
        req = urllib.request.Request(url, method='HEAD', headers={'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status == 200
    except:
        return False

def scrape_default_channel_info(page):
    print(f"\n📡 Varsayılan kanal bilgisi taranıyor...")
    try:
        page.goto(TARAFTARIUM_DOMAIN, timeout=40000, wait_until='domcontentloaded')
        time.sleep(3)
        
        iframe = page.query_selector("iframe#customIframe")
        if iframe:
            src = iframe.get_attribute('src')
            if src:
                full_url = urljoin(TARAFTARIUM_DOMAIN, src)
                qs = parse_qs(urlparse(full_url).query)
                return full_url, qs.get('id', [None])[0]
    except Exception as e:
        print(f"⚠️ Varsayılan kanal hatası: {e}")
    return None, None

def extract_base_m3u8_url(page, event_url):
    try:
        if event_url:
            page.goto(event_url, timeout=15000, wait_until="domcontentloaded")
            content = page.content()
            match = re.search(r"['\"](https?://[^'\"]+/checklist/)['\"]", content)
            if match:
                base = match.group(1)
                print(f"✅ Otomatik Base URL: {base}")
                return base
    except: pass
    
    fallback = "https://andro.1386503.xyz/checklist/"
    print(f"⚠️ Base URL bulunamadı, yedek: {fallback}")
    return fallback

def scrape_all_channels(page, base_m3u8_url):
    print(f"\n📡 Kanal listesi taranıyor...")
    channels = []
    seen_entries = set() 

    try:
        if page.url != TARAFTARIUM_DOMAIN:
            page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
        
        print("⬇️  Sayfa aşağı kaydırılıyor...")
        for _ in range(7): 
            page.mouse.wheel(0, 1500)
            time.sleep(1) 
        
        page.mouse.wheel(0, -10000)
        time.sleep(1)

        elements = page.query_selector_all("div.mac[data-url]")
        print(f"-> Toplam {len(elements)} adet yayın bulundu.")

        for el in elements:
            try:
                # 1. İsim
                name_el = el.query_selector(".takimlar")
                raw_name = name_el.inner_text().strip() if name_el else "İsimsiz Kanal"
                clean_name = raw_name.replace("CANLI", "").strip().split('\n')[0]

                # 2. Lig/Kategori
                lig_el = el.query_selector(".lig")
                lig_info = lig_el.inner_text().strip() if lig_el else ""

                # 3. Saat
                saat_el = el.query_selector(".saat")
                saat_info = saat_el.inner_text().strip() if saat_el else ""

                # Görünür İsim (Display Name)
                display_name = clean_name
                if "7/24" not in lig_info and saat_info:
                    if saat_info != "CANLI":
                        display_name = f"[{saat_info}] {clean_name}"
                    else:
                        display_name = f"[CANLI] {clean_name}"

                # 4. ID
                data_url = el.get_attribute("data-url")
                if not data_url: continue
                
                full_data_url = urljoin(TARAFTARIUM_DOMAIN, data_url)
                parsed = urlparse(full_data_url)
                stream_id = parse_qs(parsed.query).get('id', [None])[0]

                if stream_id:
                    # ID Düzeltmeleri
                    if stream_id == "androstreamlivebs1" or stream_id == "facebooklivebs1":
                        test_link = f"{base_m3u8_url}receptestt.m3u8"
                        if check_url_exists(test_link):
                            final_filename = "receptestt.m3u8"
                        else:
                            final_filename = "androstreamlivebs1.m3u8"
                    elif "androstreamlivemax" in stream_id:
                        new_id = stream_id.replace("max", "bsm")
                        final_filename = f"{new_id}.m3u8"
                    else:
                        final_filename = f"{stream_id}.m3u8"

                    entry_signature = (clean_name, final_filename)

                    if entry_signature not in seen_entries:
                        channels.append({
                            "name": clean_name,
                            "display_name": display_name,
                            "filename": final_filename,
                            "league": lig_info
                        })
                        seen_entries.add(entry_signature)

            except Exception:
                continue

        print(f"✅ {len(channels)} adet yayın işlendi.")
        return channels

    except Exception as e:
        print(f"❌ Tarama hatası: {e}")
        return []

def determine_group(channel_data):
    """
    YENİ KATEGORİ SİSTEMİ
    """
    name = channel_data['name']
    league = channel_data['league']
    n = name.lower()

    # 1. TV Kanalları (7/24 olanlar)
    if "7/24" in league:
        # --- Premium Platformlar (Ayrı Kalıyor) ---
        if "bein" in n: return "BeinSports"
        if "s sport" in n or "ssport" in n: return "S Sports"
        if "tivibu" in n: return "Tivibu"
        if "exxen" in n or "exn" in n: return "Exxen"
        if "smart" in n: return "Smart Spor"
        if "nba" in n: return "NBA"
        if "tabi" in n: return "Tabii"
        
        # --- Özel İstek: EuroSport Ayrı ---
        if "euro" in n: return "EuroSport"

        # --- BÜYÜK BİRLEŞME: TRT + Ulusal + Diğer Hepsi Buraya ---
        # Yukarıdaki if'lere girmeyen (ATV, A Spor, TRT, TV8, Kanal D vb.) herkes buraya.
        return "Ulusal ve Diğer Kanallar"
    
    # 2. Canlı Maçlar
    if league:
        return f"Canlı Maçlar - {league}"
    else:
        return "Canlı Maçlar"

def main():
    with sync_playwright() as p:
        print("🚀 Taraftarium24 Bot (Kategori Birleştirmeli) Başlatılıyor...")

        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # 1. Base URL
        default_url, _ = scrape_default_channel_info(page)
        base_m3u8_url = extract_base_m3u8_url(page, default_url)

        # 2. Tara
        channels = scrape_all_channels(page, base_m3u8_url)

        if not channels:
            print("❌ Kanal bulunamadı.")
            browser.close()
            sys.exit(1)

        # 3. Dosya Yaz
        output_filename = "kanallar4.m3u8"
        content = ["#EXTM3U", f"#EXT-X-REFERER:{TARAFTARIUM_DOMAIN}"]
        
        # Sıralama: TV Kanalları Üste, Maçlar Alta
        channels.sort(key=lambda x: ("7/24" not in x['league'], x['name']))

        print(f"\n📺 {len(channels)} yayın dosyaya yazılıyor...")
        
        for ch in channels:
            link = f"{base_m3u8_url}{ch['filename']}"
            group = determine_group(ch)
            
            content.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}",{ch["display_name"]}')
            content.append(link)

        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        print(f"📂 Dosya hazır: {output_filename}")
        browser.close()

if __name__ == "__main__":
    main()
