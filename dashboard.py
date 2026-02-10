import streamlit as st
import json
import os
import datetime
import shutil
from generate_calendar_image import generate_calendar_pdf, get_weekly_calendar_figure, get_mixed_color
from streamlit_calendar import calendar
from ics import Calendar, Event

st.set_page_config(
    page_title="BA Toplantı Yönetim Sistemi",
    page_icon="📅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Sabitler ---
JSON_FILE = 'calendar_data.json'
BACKUP_DIR = 'backups'
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]

# --- Yardımcı Fonksiyonlar ---
def get_person_names(data):
    """Kişi listesini (obje veya string) isim listesi olarak döndürür."""
    people = data.get('people', [])
    if not people:
        return []
    if isinstance(people[0], dict):
        return [p['name'] for p in people]
    return people

def load_data():
    if os.path.exists(JSON_FILE):
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            # Eksik alanları tamamla (Şema Göçü)
            if 'holidays' not in data:
                data['holidays'] = {} # YYYY-MM-DD: İsim formatında
            elif isinstance(data['holidays'], list):
                # Eski liste formatını sözlüğe çevir
                data['holidays'] = {h: "Resmi Tatil" for h in data['holidays']}
                
            if 'exceptions' not in data:
                data['exceptions'] = [] # {"date": "YYYY-MM-DD", "meeting_title": "..."}

            # People Schema Migration (String -> Object)
            if 'people' in data and len(data['people']) > 0 and isinstance(data['people'][0], str):
                new_people = []
                for p in data['people']:
                    new_people.append({
                        "name": p,
                        "fullname": p,
                        "email": ""
                    })
                data['people'] = new_people
                
            return data
    return {"settings": {}, "people": [], "meetings": [], "holidays": {}, "exceptions": []}

def save_data(data):
    # 1. Yedekleme
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"calendar_data_{timestamp}.json")
    
    # Mevcut dosyayı yedekle
    if os.path.exists(JSON_FILE):
        shutil.copy2(JSON_FILE, backup_path)
    
    # Eski yedekleri temizle (Son 10)
    backups = sorted([os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith('.json')])
    while len(backups) > 10:
        os.remove(backups.pop(0))

    # 2. Kaydetme
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def validate_time(t):
    try:
        datetime.datetime.strptime(t, "%H:%M")
        return True
    except ValueError:
        return False

# --- Sayfa Yapısı ---

st.title("📅 BA Toplantı Yönetim Sistemi")

# Veriyi Yükle
data = load_data()
if 'settings' not in data:
    st.error("Veri dosyası bozuk veya okunamadı!")
    st.stop()

# --- Sidebar ---
st.sidebar.title("Menü")
menu = st.sidebar.radio("Git:", ["Web Takvimi", "Raporlar", "Takvim Yönetimi", "Kullanıcılar", "Ayarlar & Tatiller"])

st.sidebar.markdown("---")
st.sidebar.info("💡 **İpucu:** Değişiklikler anında kaydedilmez, butonlara basmayı unutmayın.")

# --- 1. WEB TAKVİMİ ---
if menu == "Web Takvimi":
    st.header("🖥️ Web Takvimi Görünümü")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        people_names = get_person_names(data)
        people_list = ["Tümü"] + people_names
        selected_person = st.selectbox("Kimin Takvimi?", people_list, key="web_cal_person")
        
        # Görünüm Modu
        view_mode = st.selectbox("Görünüm", ["Haftalık (Etkileşimli)", "Aylık (Etkileşimli)", "Klasik (Resim)"])
        
        # ICS Export
        if st.button("📅 Outlook ICS İndir"):
            c = Calendar()
            today = datetime.date.today()
            # Bu yılın tamamı için
            start_range = datetime.date(today.year, 1, 1)
            end_range = datetime.date(today.year, 12, 31)
            
            st.info("ICS dosyası hazırlanıyor, lütfen bekleyin...")
            
            # Kişi Haritası (Email için)
            person_map = {}
            for p in data.get('people', []):
                if isinstance(p, dict):
                    person_map[p['name']] = p
            
            # Tatiller
            for h_date_str, h_name in data.get('holidays', {}).items():
                try:
                    e = Event()
                    e.name = f"Tatil: {h_name}"
                    e.begin = h_date_str
                    e.make_all_day()
                    c.events.add(e)
                except:
                    pass
            
            # Toplantılar
            day_count = (end_range - start_range).days
            count = 0
            
            for i in range(day_count + 1):
                curr = start_range + datetime.timedelta(days=i)
                
                # Haftasonu Kontrolü (Haftasonları atla)
                if curr.weekday() >= 5: continue
                
                day_str = TR_DAYS[curr.weekday()]
                d_str = curr.strftime("%Y-%m-%d")
                
                # Tatil Kontrolü
                if d_str in data.get('holidays', {}): continue
                
                for m in data['meetings']:
                    if m['day'] != day_str: continue
                    
                    try:
                        m_start = datetime.datetime.strptime(m['start_date'], "%Y-%m-%d").date()
                        m_end = datetime.datetime.strptime(m['end_date'], "%Y-%m-%d").date()
                    except:
                        continue
                        
                    if not (m_start <= curr <= m_end): continue
                    
                    # Sıklık
                    show = False
                    if m['frequency'] == "Her Hafta": show = True
                    elif m['frequency'] == "İki Haftada Bir":
                        if ((curr - m_start).days // 7) % 2 == 0: show = True
                    elif m['frequency'] == "Tek Seferlik":
                        if curr == m_start: show = True
                    
                    if show:
                        try:
                            e = Event()
                            e.name = m['title']
                            
                            # Zaman
                            s_dt = datetime.datetime.combine(curr, datetime.datetime.strptime(m['start_time'], "%H:%M").time())
                            e_dt = datetime.datetime.combine(curr, datetime.datetime.strptime(m['end_time'], "%H:%M").time())
                            # ICS kütüphanesi timezone aware bekleyebilir, arrow kullanıyor
                            e.begin = s_dt
                            e.end = e_dt
                            
                            atts = m.get('attendees', [])
                            desc = f"Toplantı: {m['title']}\nKatılımcılar: {', '.join(atts)}"
                            e.description = desc
                            
                            # Email ekleme (Opsiyonel, kütüphane desteğine bağlı)
                            # ics kütüphanesinde attendee ekleme biraz farklı olabilir, description'a ekledik şimdilik.
                            
                            c.events.add(e)
                            count += 1
                        except Exception as err:
                            print(f"Hata: {err}")
                            continue

            st.success(f"{count} etkinlik hazırlandı.")
            st.download_button("📥 İndir (.ics)", c.serialize(), file_name="takvim.ics", mime="text/calendar")
            
    with col2:
        if "Etkileşimli" in view_mode:
            # Streamlit Calendar Implementation
            calendar_events = []
            
            # Tatilleri Ekle
            holidays = data.get('holidays', {})
            for h_date, h_name in holidays.items():
                calendar_events.append({
                    "title": f"🌴 {h_name}",
                    "start": h_date,
                    "allDay": True,
                    "backgroundColor": "#FFEBEE",
                    "borderColor": "#FFCDD2",
                    "textColor": "#B71C1C",
                    "display": "background"
                })

            # Toplantıları Ekle
            # 3 Aylık bir pencere için hesaplayalım (Performans için)
            base_date = datetime.date.today()
            calc_start = base_date - datetime.timedelta(days=30)
            calc_end = base_date + datetime.timedelta(days=90)
            
            day_count = (calc_end - calc_start).days
            
            for i in range(day_count + 1):
                curr_date = calc_start + datetime.timedelta(days=i)
                day_str = TR_DAYS[curr_date.weekday()]
                date_str = curr_date.strftime("%Y-%m-%d")
                
                # Tatil kontrolü
                if date_str in holidays:
                    continue
                    
                if curr_date.weekday() >= 5: # Haftasonu
                    continue
                
                # O günün toplantılarını bul
                for m in data['meetings']:
                    # Filtreleme
                    if selected_person != "Tümü" and selected_person not in m.get('attendees', []):
                        continue
                        
                    # Gün kontrolü
                    if m['day'] != day_str:
                        continue
                        
                    # Tarih aralığı kontrolü
                    m_start_date = datetime.datetime.strptime(m['start_date'], "%Y-%m-%d").date()
                    m_end_date = datetime.datetime.strptime(m['end_date'], "%Y-%m-%d").date()
                    
                    if not (m_start_date <= curr_date <= m_end_date):
                        continue
                        
                    # Sıklık Kontrolü
                    show = False
                    if m['frequency'] == "Her Hafta":
                        show = True
                    elif m['frequency'] == "İki Haftada Bir":
                        weeks_diff = (curr_date - m_start_date).days // 7
                        if weeks_diff % 2 == 0:
                            show = True
                    elif m['frequency'] == "Tek Seferlik":
                        if curr_date == m_start_date:
                            show = True
                    elif m['frequency'] == "Aylık":
                        # Basit mantık: her 4 haftada bir veya ayın aynı günü?
                        # Mevcut sistemde net değil, "4 haftada bir" varsayımı yapılıyor genelde
                        # veya ayın aynı günü. Kodda generate_calendar_image.py ne yapıyor?
                        # O sadece haftalık bakıyor. Biz de basit tutalım.
                        pass 
                    
                    if show:
                        # Renk
                        atts = m.get('attendees', [])
                        if len(atts) == 1:
                            color = data['settings']['colors'].get(atts[0], {}).get('bg', '#CCCCCC')
                        elif set(atts) == set(["Özden", "Burak", "Doğukan"]): # Tüm Ekip (Hardcoded logic from json)
                            color = data['settings']['colors'].get("All Team", {}).get('bg', '#FFCCCC')
                        else:
                            color = "#E0E0E0" # Mixed
                            
                        calendar_events.append({
                            "title": m['title'],
                            "start": f"{date_str}T{m['start_time']}",
                            "end": f"{date_str}T{m['end_time']}",
                            "backgroundColor": color,
                            "borderColor": "#666666",
                            "textColor": "#000000",
                            "extendedProps": {
                                "attendees": ", ".join(atts),
                                "description": f"{m['title']} ({m['start_time']}-{m['end_time']})"
                            }
                        })

            mode = "timeGridWeek" if "Haftalık" in view_mode else "dayGridMonth"
            
            calendar_options = {
                "initialView": mode,
                "headerToolbar": {
                    "left": "prev,next today",
                    "center": "title",
                    "right": "dayGridMonth,timeGridWeek,timeGridDay"
                },
                "slotMinTime": "08:00:00",
                "slotMaxTime": "18:00:00",
                "allDaySlot": False,
                "locale": "tr",
                "firstDay": 1, # Pazartesi
                "eventClick": {"function": "alert(event.event.extendedProps.description)"} # Basit tooltip alert
            }
            
            # Click to edit için custom JS gerekebilir ama şimdilik basic
            custom_css = """
                .fc-event-title { font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
                .fc-event:hover::after { content: attr(title); position: absolute; z-index: 100; background: black; color: white; padding: 5px; }
            """
            
            calendar(events=calendar_events, options=calendar_options, custom_css=custom_css)
            
        else:
            # Klasik Görünüm
            start_date = st.date_input("Hafta Başlangıç Tarihi", datetime.date.today(), key="web_cal_date")
            with st.spinner('Takvim hazırlanıyor...'):
                filter_person = None if selected_person == "Tümü" else selected_person
                fig = get_weekly_calendar_figure(data=data, start_date=start_date, user_filter=filter_person)
                st.pyplot(fig)

# --- 2. RAPORLAR ---
elif menu == "Raporlar":
    st.header("📄 PDF Rapor Üretimi")
    
    people_names = get_person_names(data)
    people_list = ["Tümü"] + people_names
    selected_person = st.selectbox("Kimin Takvimi?", people_list)
    
    start_date = st.date_input("Başlangıç Tarihi", datetime.date.today())
    
    if st.button("PDF Oluştur", type="primary"):
        with st.spinner('PDF hazırlanıyor...'):
            try:
                filter_person = None if selected_person == "Tümü" else selected_person
                output_file = generate_calendar_pdf(data=data, start_date=start_date, user_filter=filter_person)
                
                st.success(f"Başarılı! Dosya oluşturuldu: {output_file}")
                
                with open(output_file, "rb") as pdf_file:
                    PDFbyte = pdf_file.read()

                st.download_button(label="📥 PDF İndir",
                                   data=PDFbyte,
                                   file_name=output_file,
                                   mime='application/octet-stream')
                                   
            except Exception as e:
                st.error(f"Hata oluştu: {e}")

# --- 3. TAKVİM YÖNETİMİ ---
elif menu == "Takvim Yönetimi":
    st.header("📝 Toplantı Yönetimi")
    
    tab1, tab2 = st.tabs(["Toplantı Listesi & Düzenle", "Yeni Toplantı Ekle"])
    
    with tab1:
        if not data['meetings']:
            st.info("Henüz hiç toplantı yok.")
        else:
            for i, m in enumerate(data['meetings']):
                with st.expander(f"{m['title']} ({m['day']} {m['start_time']}-{m['end_time']})"):
                    with st.form(key=f"edit_form_{i}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            new_title = st.text_input("Başlık", m['title'])
                            new_day = st.selectbox("Gün", TR_DAYS, index=TR_DAYS.index(m['day']) if m['day'] in TR_DAYS else 0)
                            new_freq = st.selectbox("Sıklık", 
                                                  ["Tek Seferlik", "Her Hafta", "İki Haftada Bir", "Aylık", "Aylık (Son Pazartesi)"],
                                                  index=["Tek Seferlik", "Her Hafta", "İki Haftada Bir", "Aylık", "Aylık (Son Pazartesi)"].index(m['frequency']) if m['frequency'] in ["Tek Seferlik", "Her Hafta", "İki Haftada Bir", "Aylık", "Aylık (Son Pazartesi)"] else 0)
                        
                        with col2:
                            new_start = st.text_input("Başlangıç (HH:MM)", m['start_time'])
                            new_end = st.text_input("Bitiş (HH:MM)", m['end_time'])
                            new_attendees = st.multiselect("Katılımcılar", data['people'], default=[p for p in m['attendees'] if p in data['people']])
                        
                        new_start_date = st.date_input("Başlangıç Tarihi", datetime.datetime.strptime(m.get('start_date', '2026-01-01'), "%Y-%m-%d").date())
                        new_end_date = st.date_input("Bitiş Tarihi (Opsiyonel)", datetime.datetime.strptime(m.get('end_date', '2026-12-31'), "%Y-%m-%d").date())

                        c1, c2 = st.columns([1, 4])
                        with c1:
                            submitted = st.form_submit_button("Kaydet", type="primary")
                        with c2:
                            delete_btn = st.form_submit_button("Sil", type="secondary")
                        
                        if submitted:
                            if not validate_time(new_start) or not validate_time(new_end):
                                st.error("Saat formatı hatalı! (HH:MM)")
                            elif new_end <= new_start:
                                st.error("Bitiş saati başlangıçtan büyük olmalı!")
                            else:
                                data['meetings'][i] = {
                                    "title": new_title,
                                    "day": new_day,
                                    "start_time": new_start,
                                    "end_time": new_end,
                                    "frequency": new_freq,
                                    "attendees": new_attendees,
                                    "start_date": new_start_date.strftime("%Y-%m-%d"),
                                    "end_date": new_end_date.strftime("%Y-%m-%d")
                                }
                                save_data(data)
                                st.success("Toplantı güncellendi!")
                                st.rerun()
                        
                        if delete_btn:
                            data['meetings'].pop(i)
                            save_data(data)
                            st.warning("Toplantı silindi!")
                            st.rerun()

    with tab2:
        st.subheader("Yeni Toplantı")
        with st.form("add_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Toplantı Başlığı")
                day = st.selectbox("Gün", TR_DAYS)
                freq = st.selectbox("Sıklık", ["Her Hafta", "İki Haftada Bir", "Tek Seferlik", "Aylık"])
            
            with col2:
                s_time = st.text_input("Başlangıç (HH:MM)", "09:00")
                e_time = st.text_input("Bitiş (HH:MM)", "10:00")
                atts = st.multiselect("Katılımcılar", get_person_names(data))
            
            s_date = st.date_input("Başlangıç Tarihi", datetime.date.today())
            
            added = st.form_submit_button("Ekle")
            
            if added:
                if not title:
                    st.error("Başlık giriniz.")
                elif not validate_time(s_time) or not validate_time(e_time):
                    st.error("Saat formatı hatalı.")
                elif e_time <= s_time:
                    st.error("Bitiş saati başlangıçtan büyük olmalı.")
                else:
                    new_meeting = {
                        "title": title,
                        "day": day,
                        "start_time": s_time,
                        "end_time": e_time,
                        "frequency": freq,
                        "attendees": atts,
                        "start_date": s_date.strftime("%Y-%m-%d"),
                        "end_date": "2026-12-31"
                    }
                    data['meetings'].append(new_meeting)
                    save_data(data)
                    st.success("Toplantı eklendi!")
                    st.rerun()

# --- 4. KULLANICILAR ---
elif menu == "Kullanıcılar":
    st.header("👥 Kullanıcı Yönetimi")
    st.info("Kullanıcı bilgilerini (Tam Ad, E-Posta) buradan düzenleyebilirsiniz. Yeni satır ekleyerek kullanıcı oluşturabilirsiniz.")
    
    # Mevcut Veri
    people_data = data.get('people', [])
    
    # Editör
    edited_people = st.data_editor(
        people_data,
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn("Kısa Ad (ID)", help="Sistemde kullanılan kısa ad (Örn: Özden)", required=True),
            "fullname": st.column_config.TextColumn("Tam Ad", help="Raporda ve ICS'de görünecek tam ad"),
            "email": st.column_config.TextColumn("E-Posta", help="ICS davetleri için e-posta adresi")
        },
        use_container_width=True,
        key="people_editor"
    )
    
    if st.button("💾 Değişiklikleri Kaydet", type="primary"):
        # Validasyon
        valid = True
        seen_names = set()
        
        # Boş liste kontrolü
        if not edited_people:
            data['people'] = []
            save_data(data)
            st.success("Tüm kullanıcılar silindi.")
            st.rerun()
            
        for p in edited_people:
            name = p.get('name', '').strip()
            if not name:
                st.error("Kısa Ad (ID) boş olamaz!")
                valid = False
                break
            if name in seen_names:
                st.error(f"Tekrar eden isim bulundu: {name}")
                valid = False
                break
            seen_names.add(name)
            p['name'] = name # Strip edilmiş hali
            
        if valid:
            # Yeni kullanıcılar için renk ata
            # Eski isimler (dict listesinden isimleri çek)
            # data['people'] henüz güncellenmedi, içindeki eski listeye bakıyoruz
            old_names = set()
            if data['people'] and isinstance(data['people'][0], dict):
                old_names = set([p['name'] for p in data['people']])
            elif data['people']:
                old_names = set(data['people']) # String listesiyse (migration öncesi ama load_data yaptı)
            
            new_names = seen_names
            
            for name in new_names:
                if name not in old_names:
                    # Yeni kullanıcı, renk ata
                    import random
                    color = "#{:06x}".format(random.randint(0, 0xFFFFFF))
                    if 'colors' not in data['settings']:
                        data['settings']['colors'] = {}
                    data['settings']['colors'][name] = {"bg": color, "border": color, "label": name}
            
            # Kaydet
            data['people'] = edited_people
            save_data(data)
            st.success("Kullanıcı listesi başarıyla güncellendi!")
            st.rerun()

# --- 5. AYARLAR & TATİLLER ---
elif menu == "Ayarlar & Tatiller":
    st.header("⚙️ Ayarlar ve İstisnalar")
    
    st.subheader("🚫 Resmi Tatiller / İptaller")
    st.write("Bu tarihlerdeki toplantılar takvimde oluşturulmayacak ve 'RESMİ TATİL' olarak işaretlenecek.")
    
    # Tatil Listesi (Sözlük)
    holidays = data.get('holidays', {})
    
    # Yeni Tatil Ekle
    with st.form("new_holiday_form"):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            new_holiday_date = st.date_input("Tatil Tarihi Ekle")
        with c2:
            new_holiday_name = st.text_input("Tatil Adı (Opsiyonel)", "Resmi Tatil")
        with c3:
            add_h_btn = st.form_submit_button("Ekle")
            
        if add_h_btn:
            d_str = new_holiday_date.strftime("%Y-%m-%d")
            holidays[d_str] = new_holiday_name
            # Sıralama (görsel amaçlı sözlük sıralı olmayabilir ama key'e göre sıralı tutabiliriz)
            # JSON'a kaydederken sıra önemli değil ama okurken sort edebiliriz.
            data['holidays'] = dict(sorted(holidays.items()))
            save_data(data)
            st.success("Eklendi.")
            st.rerun()
    
    # Listele ve Sil
    if holidays:
        st.write("Kayıtlı Tatiller:")
        # Tarihe göre sıralı listeleme
        sorted_dates = sorted(holidays.keys())
        for d_str in sorted_dates:
            name = holidays[d_str]
            col_a, col_b, col_c = st.columns([2, 4, 1])
            col_a.text(d_str)
            col_b.text(name)
            if col_c.button("Sil", key=f"del_h_{d_str}"):
                del holidays[d_str]
                data['holidays'] = holidays
                save_data(data)
                st.rerun()
    else:
        st.info("Kayıtlı tatil yok.")

    st.markdown("---")
    st.subheader("Tekil Toplantı İptalleri (Exceptions)")
    st.info("Bu özellik yapım aşamasında. Şimdilik 'Tatiller' kısmını kullanarak o günkü tüm toplantıları iptal edebilirsiniz.")
