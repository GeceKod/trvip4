import re
import sys
import time
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# ---------------- AYARLAR ----------------
TARAFTARIUM_DOMAIN = "https://taraftarium24.xyz/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
OUTPUT_FILENAME = "kanallar4.m3u8"

def get_channel_group(channel_name):
    """Kanal ismine göre otomatik kategori belirler"""
    name_lower = channel_name.lower()
    if "bein" in name_lower:
        return "BeinSports"
    elif "s sport" in name_lower or "ssport" in name_lower:
        return "S Sports"
    elif "tivibu" in name_lower:
        return "Tivibu"
    elif "exxen" in name_lower:
        return "Exxen"
    elif "smart" in name_lower or "d-smart" in name_lower:
        return "Smart Spor"
    elif "nba" in name_lower:
        return "NBA"
    elif "trt" in name_lower:
        return "TRT"
    elif "eurosport" in name_lower:
        return "EuroSport"
    else:
        return "Ulusal/Diğer"

def scrape_channels(page):
    """Sitedeki tüm kanal linklerini otomatik bulur"""
    print("📡 Kanallar siteden otomatik taranıyor...")
    channels = []
    seen_ids = set() # Aynı kanalı iki kez eklememek için

    try:
        # Kanal linklerini taşıyan elementleri bul (href içinde 'id=' olanlar)
        # Genellikle sidebar veya menüdedirler.
        links = page.query_selector_all("a[href*='channel.html?id=']")
        
        print(f"   -> Toplam {len(links)} adet potansiyel kanal linki bulundu.")

        for link in links:
            href = link.get_attribute("href")
            name = link.inner_text().strip()
            
            # Kanal isminde gereksiz boşluk veya yeni satır varsa temizle
            name = re.sub(r'\s+', ' ', name)

            # URL'den ID'yi çek
            match = re.search(r'id=([a-zA-Z0-9_]+)', href)
            if match and name:
                c_id = match.group(1)
                
                # --- ID DÜZELTMELERİ (Sitedeki link eski, player yeni olabilir) ---
                # Örnek: Site max1 der ama player bsm1 ister.
                if "androstreamlivemax" in c_id:
                    c_id = c_id.replace("max", "bsm")
                
                if c_id not in seen_ids:
                    channels.append({"id": c_id, "name": name})
                    seen_ids.add(c_id)
    except Exception as e:
        print(f"⚠️ Kanal tarama hatası: {e}")

    # Eğer hiç kanal bulamazsa manuel listeyi devreye sokabiliriz (Opsiyonel)
    if not channels:
        print("❌ Otomatik tarama başarısız oldu veya kanal bulunamadı.")
    else:
        print(f"✅ {len(channels)} adet benzersiz kanal başarıyla listelendi.")
        
    return channels

def find_base_url(page):
    """Base URL bulma fonksiyonu"""
    print(f"🔍 Base URL taranıyor...")
    try:
        content = page.content()
        pattern = re.compile(r'https://andro\.[0-9]+\.xyz/checklist/')
        match = pattern.search(content)
        if match:
            found_url = match.group(0)
            print(f"✅ Otomatik Base URL bulundu: {found_url}")
            return found_url
    except Exception as e:
        print(f"⚠️ Base URL taramasında hata: {e}")

    FALLBACK_URL = "https://andro.1386503.xyz/checklist/"
    print(f"⚠️ Base URL bulunamadı, varsayılan kullanılıyor: {FALLBACK_URL}")
    return FALLBACK_URL

def main():
    print("🚀 Taraftarium24 Otomatik M3U8 Botu Başlatılıyor...")
    
    with sync_playwright() as p:
        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--autoplay-policy=no-user-gesture-required'
        ]
        
        browser = p.chromium.launch(headless=True, args=browser_args)
        context = browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
        page = context.new_page()

        try:
            print(f"🌐 Siteye bağlanılıyor: {TARAFTARIUM_DOMAIN}")
            page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
            
            # 1. Base URL'i Bul
            base_m3u8_url = find_base_url(page)
            
            # 2. Kanalları Otomatik Çek
            channel_list = scrape_channels(page)

        except PlaywrightError as e:
            print(f"❌ Siteye bağlanırken kritik hata: {e}")
            browser.close()
            sys.exit(1)

        # 3. M3U8 Dosyasını Oluştur
        m3u_content = []
        created_count = 0
        
        print(f"\n📺 Linkler işleniyor...")

        for channel in channel_list:
            c_name = channel['name']
            c_id = channel['id']
            c_group = get_channel_group(c_name)
            
            # --- ÖZEL DOSYA İSMİ KURALLARI ---
            # BeIN Sports 1 için özel durum
            if c_id == "androstreamlivebs1" or c_id == "facebooklivebs1":
                final_filename = "receptestt.m3u8"
            else:
                final_filename = f"{c_id}.m3u8"
            
            full_link = f"{base_m3u8_url}{final_filename}"
            
            m3u_content.append(f'#EXTINF:-1 tvg-name="{c_name}" group-title="{c_group}",{c_name}')
            m3u_content.append(full_link)
            created_count += 1

        browser.close()

        if created_count > 0:
            header = f"""#EXTM3U
#EXT-X-USER-AGENT:{USER_AGENT}
#EXT-X-REFERER:{TARAFTARIUM_DOMAIN}
#EXT-X-ORIGIN:{TARAFTARIUM_DOMAIN.rstrip('/')}"""
            
            with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
                f.write(header)
                f.write("\n")
                f.write("\n".join(m3u_content))
            
            print(f"\n✅ {created_count} kanal başarıyla '{OUTPUT_FILENAME}' dosyasına kaydedildi.")
        else:
            print("\n❌ Hiçbir kanal oluşturulamadı.")

        print("\n" + "="*50)
        print("🎉 İşlem Tamamlandı!")

if __name__ == "__main__":
    main()
