import re
import sys
import time
from playwright.sync_api import sync_playwright, Error as PlaywrightError

# ---------------- AYARLAR ----------------
# Ana site adresi (Gerekirse güncelleyebilirsiniz)
TARAFTARIUM_DOMAIN = "https://taraftarium24.xyz/"

# Tarayıcı Kimliği
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# KANALLAR LISTESI (ID ve İsim Eşleşmeleri)
# Not: "androstreamlivebs1" ID'si kod içinde özel olarak yakalanıp "receptestt.m3u8"e çevrilecektir.
CHANNELS = [
    {"id": "androstreamlivebs1", "name": "BeIN Sports 1", "group": "BeinSports"},
    {"id": "androstreamlivebs2", "name": "BeIN Sports 2", "group": "BeinSports"},
    {"id": "androstreamlivebs3", "name": "BeIN Sports 3", "group": "BeinSports"},
    {"id": "androstreamlivebs4", "name": "BeIN Sports 4", "group": "BeinSports"},
    {"id": "androstreamlivebs5", "name": "BeIN Sports 5", "group": "BeinSports"},
    {"id": "androstreamlivemax1", "name": "BeIN Sports Max 1", "group": "BeinSports"},
    {"id": "androstreamlivemax2", "name": "BeIN Sports Max 2", "group": "BeinSports"},
    {"id": "androstreamlivess1", "name": "S Sport", "group": "S Sports"},
    {"id": "androstreamlivess2", "name": "S Sport 2", "group": "S Sports"},
    {"id": "androstreamlivetivibu1", "name": "Tivibu Spor 1", "group": "Tivibu"},
    {"id": "androstreamlivetivibu2", "name": "Tivibu Spor 2", "group": "Tivibu"},
    {"id": "androstreamlivetivibu3", "name": "Tivibu Spor 3", "group": "Tivibu"},
    {"id": "androstreamlivenbatv", "name": "NBA TV", "group": "NBA"},
    {"id": "androstreamliveexxen1", "name": "Exxen Spor 1", "group": "Exxen"},
    {"id": "androstreamliveexxen2", "name": "Exxen Spor 2", "group": "Exxen"},
    {"id": "androstreamliveexxen3", "name": "Exxen Spor 3", "group": "Exxen"},
    {"id": "androstreamliveexxen4", "name": "Exxen Spor 4", "group": "Exxen"},
    {"id": "androstreamlivesmartsbo", "name": "Smart Spor", "group": "Smart Spor"},
    {"id": "androstreamlivetrtspor", "name": "TRT Spor", "group": "TRT"},
    {"id": "androstreamlivetrtspor2", "name": "TRT Spor Yildiz", "group": "TRT"},
]

def find_base_url(page):
    """
    Sayfa kaynağındaki 'const baseurls' dizisini veya tekil 'baseurl' değişkenini bulur.
    Bulamazsa çalışan bilinen bir adresi döndürür.
    """
    print(f"🔍 Base URL taranıyor...")
    
    # 1. Yöntem: Sitedeki 'const baseurls = [...]' dizisinden rastgele bir tane seçmek yerine ilkini alalım.
    try:
        content = page.content()
        
        # Regex ile 'andro.xxxx.xyz/checklist/' formatındaki linkleri ara
        # Örnek: https://andro.1386503.xyz/checklist/
        pattern = re.compile(r'https://andro\.[0-9]+\.xyz/checklist/')
        match = pattern.search(content)
        
        if match:
            found_url = match.group(0)
            print(f"✅ Otomatik Base URL bulundu: {found_url}")
            return found_url
            
    except Exception as e:
        print(f"⚠️ Base URL taramasında hata: {e}")

    # 2. Yöntem: Eğer bulamazsak, sizin verdiğiniz çalışan linki varsayılan olarak kullan.
    # Bu domainler sık değişse de genelde checklist yapısı aynı kalır.
    FALLBACK_URL = "https://andro.1386503.xyz/checklist/"
    print(f"⚠️ Base URL bulunamadı, varsayılan kullanılıyor: {FALLBACK_URL}")
    return FALLBACK_URL

def main():
    print("🚀 Taraftarium24 M3U8 Oluşturucu Başlatılıyor...")
    
    with sync_playwright() as p:
        # Tarayıcı başlatma ayarları (Headless: Arka planda çalışır)
        browser_args = [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--autoplay-policy=no-user-gesture-required'
        ]
        
        browser = p.chromium.launch(headless=True, args=browser_args)
        context = browser.new_context(user_agent=USER_AGENT, ignore_https_errors=True)
        page = context.new_page()

        # 1. Adım: Siteye git ve Base URL'i öğren
        try:
            print(f"🌐 Siteye bağlanılıyor: {TARAFTARIUM_DOMAIN}")
            # Önce ana sayfaya git
            page.goto(TARAFTARIUM_DOMAIN, timeout=30000, wait_until='domcontentloaded')
            
            # İçerikteki bir kanal iframe'ine veya sayfasına ulaşmaya çalışalım
            # Genelde bir kanala tıklamak gerekir ama kaynak kodda varsa direkt alırız.
            # Kodumuz direkt kaynak koddan baseurl çekmeye çalışacak.
            
            base_m3u8_url = find_base_url(page)
            
        except PlaywrightError as e:
            print(f"❌ Siteye bağlanırken hata oluştu: {e}")
            # Hata olsa bile fallback URL ile devam etmeyi dene
            base_m3u8_url = "https://andro.1386503.xyz/checklist/"

        # 2. Adım: Linkleri Oluştur
        m3u_content = []
        created_count = 0
        
        print(f"\n📺 {len(CHANNELS)} kanal işleniyor...")

        for channel in CHANNELS:
            c_name = channel['name']
            c_id = channel['id']
            c_group = channel['group']
            
            # --- KRİTİK DÜZELTME BURADA ---
            # Sitenin JavaScript mantığındaki özel durumu buraya ekledik.
            if c_id == "androstreamlivebs1" or c_id == "facebooklivebs1":
                final_filename = "receptestt.m3u8"
                print(f"   -> [ÖZEL] {c_name} için dosya adı düzeltildi: {final_filename}")
            else:
                final_filename = f"{c_id}.m3u8"
            
            # Tam linki oluştur
            full_link = f"{base_m3u8_url}{final_filename}"
            
            # M3U formatına ekle
            m3u_content.append(f'#EXTINF:-1 tvg-name="{c_name}" group-title="{c_group}",{c_name}')
            m3u_content.append(full_link)
            created_count += 1

        browser.close()

        # 3. Adım: Dosyayı Kaydet
        output_filename = "kanallar.m3u8"
        if created_count > 0:
            header = f"""#EXTM3U
#EXT-X-USER-AGENT:{USER_AGENT}
#EXT-X-REFERER:{TARAFTARIUM_DOMAIN}
#EXT-X-ORIGIN:{TARAFTARIUM_DOMAIN.rstrip('/')}"""
            
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write(header)
                f.write("\n")
                f.write("\n".join(m3u_content))
            
            print(f"\n✅ {created_count} kanal başarıyla '{output_filename}' dosyasına kaydedildi.")
            print(f"📂 Dosya konumu: {output_filename}")
        else:
            print("\n❌ Hiçbir kanal oluşturulamadı.")

        print("\n" + "="*50)
        print("🎉 İşlem Tamamlandı!")

if __name__ == "__main__":
    main()
