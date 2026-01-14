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
    """Base URL bulucu"""
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
    print(f"\n📡 Kanal listesi taranıyor (Auto-Scroll Aktif)...")
    channels = []
    seen_ids = set()

    try:
        if page.url != TARAFTARIUM_DOMAIN:
            page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
        
        # --- ÖNEMLİ: SAYFAYI AŞAĞI KAYDIRMA (LAZY LOADING İÇİN) ---
        print("⬇️  Sayfa aşağı kaydırılıyor (Tüm listenin yüklenmesi için)...")
        for _ in range(7): # 7 kere aşağı scroll yap
            page.mouse.wheel(0, 1500)
            time.sleep(1) # Yüklenmesi için bekle
        
        # En tepeye geri çık (Garanti olsun)
        page.mouse.wheel(0, -10000)
        time.sleep(1)

        # HTML yapısına uygun genel seçici
        # class="mac" olan ve data-url özelliği bulunan DIV'leri seç
        elements = page.query_selector_all("div.mac[data-url]")
        
        print(f"-> Toplam {len(elements)} adet yayın bulundu.")

        for el in elements:
            try:
                # 1. İsim Çekme
                name_el = el.query_selector(".takimlar")
                raw_name = name_el.inner_text().strip() if name_el else "İsimsiz Kanal"
                clean_name = raw_name.replace("CANLI", "").strip().split('\n')[0]

                # 2. ID Çekme
                data_url = el.get_attribute("data-url")
                if not data_url: continue
                
                # data-url="/event.html?id=androstreamliveatv" -> ID'yi al
                full_data_url = urljoin(TARAFTARIUM_DOMAIN, data_url)
                parsed = urlparse(full_data_url)
                stream_id = parse_qs(parsed.query).get('id', [None])[0]

                if stream_id:
                    # DEBUG: ATV'yi görüp görmediğini kontrol edelim
                    if "atv" in stream_id or "Atv" in clean_name:
                        print(f"   👀 GÖZLEM: {clean_name} bulundu (ID: {stream_id})")

                    # --- ID DÜZELTMELERİ ---
                    if stream_id == "androstreamlivebs1" or stream_id == "facebooklivebs1":
                        test_link = f"{base_m3u8_url}receptestt.m3u8"
                        if "receptestt.m3u8" not in seen_ids:
                            if check_url_exists(test_link):
                                final_filename = "receptestt.m3u8"
                            else:
                                final_filename = "androstreamlivebs1.m3u8"
                        else: continue 

                    elif "androstreamlivemax" in stream_id:
                        new_id = stream_id.replace("max", "bsm")
                        final_filename = f"{new_id}.m3u8"
                    
                    else:
                        final_filename = f"{stream_id}.m3u8"

                    # Listeye Ekle
                    if final_filename not in seen_ids:
                        channels.append({
                            "name": clean_name,
                            "filename": final_filename
                        })
                        seen_ids.add(final_filename)

            except Exception:
                continue

        print(f"✅ {len(channels)} adet benzersiz kanal başarıyla listelendi.")
        return channels

    except Exception as e:
        print(f"❌ Tarama hatası: {e}")
        return []

def get_channel_group(channel_name):
    n = channel_name.lower()
    if "bein" in n: return "BeinSports"
    if "s sport" in n or "ssport" in n: return "S Sports"
    if "tivibu" in n: return "Tivibu"
    if "exxen" in n or "exn" in n: return "Exxen"
    if "smart" in n: return "Smart Spor"
    if "nba" in n: return "NBA"
    if "trt" in n: return "TRT"
    if "tabi" in n: return "Tabii"
    if any(x in n for x in ["atv", "a spor", "tv8", "kanal d", "show", "star", "fox", "now"]): return "Ulusal"
    return "Diğer"

def main():
    with sync_playwright() as p:
        print("🚀 Taraftarium24 Scroll Botu Başlatılıyor...")

        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        # 1. Base URL
        default_url, _ = scrape_default_channel_info(page)
        base_m3u8_url = extract_base_m3u8_url(page, default_url)

        # 2. Tara (Scroll ile)
        channels = scrape_all_channels(page, base_m3u8_url)

        if not channels:
            print("❌ Kanal bulunamadı.")
            browser.close()
            sys.exit(1)

        # 3. Dosya Yaz
        output_filename = "kanallar4.m3u8"
        content = ["#EXTM3U", f"#EXT-X-REFERER:{TARAFTARIUM_DOMAIN}"]
        
        # Ulusal kanalları öne alalım ki görebilesiniz
        channels.sort(key=lambda x: (get_channel_group(x['name']) != "Ulusal", x['name']))

        print(f"\n📺 {len(channels)} kanal dosyaya yazılıyor...")
        
        for ch in channels:
            link = f"{base_m3u8_url}{ch['filename']}"
            group = get_channel_group(ch['name'])
            content.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{group}",{ch["name"]}')
            content.append(link)

        with open(output_filename, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

        print(f"📂 Dosya hazır: {output_filename}")
        browser.close()

if __name__ == "__main__":
    main()
