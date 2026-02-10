import json
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.font_manager import FontProperties
from matplotlib.backends.backend_pdf import PdfPages
import textwrap
import datetime
import calendar
import os

# Türkçe gün ve ay isimleri
TR_DAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
TR_MONTHS = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", 
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

def time_to_min(t):
    h, m = map(int, t.split(':'))
    return h * 60 + m

def get_last_monday(year, month):
    """Verilen yıl ve ayın son pazartesi gününün tarihini döndürür."""
    # Bir sonraki ayın ilk gününü bul
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    
    # Geriye doğru giderek ilk pazartesiyi bul
    current_day = next_month - datetime.timedelta(days=1)
    while current_day.weekday() != 0: # 0 = Pazartesi
        current_day -= datetime.timedelta(days=1)
    return current_day

def should_show_meeting(meeting, week_start_date):
    """
    Bir toplantının verilen haftada gösterilip gösterilmeyeceğini belirler.
    week_start_date: O haftanın Pazartesi günü (datetime.date objesi)
    """
    freq = meeting.get('frequency', 'Her Hafta')
    start_date_str = meeting.get('start_date', '2026-02-02')
    end_date_str = meeting.get('end_date', '2026-12-31')
    
    try:
        meeting_start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        meeting_end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        return True # Hata durumunda göster
    
    # Toplantı başlangıç tarihinin olduğu haftanın pazartesisi
    meeting_start_week = meeting_start_date - datetime.timedelta(days=meeting_start_date.weekday())
    
    # Hafta farkı
    weeks_diff = (week_start_date - meeting_start_week).days // 7
    
    if weeks_diff < 0:
        return False # Henüz başlamadı
    
    # Bu hafta içinde hangi gün?
    meeting_day_name = meeting.get('day', '').strip()
    meeting_date_this_week = None
    
    if meeting_day_name in TR_DAYS:
        day_idx = TR_DAYS.index(meeting_day_name)
        meeting_date_this_week = week_start_date + datetime.timedelta(days=day_idx)

    show_this_week = False

    if freq == "Her Hafta":
        show_this_week = True
    elif freq == "İki Haftada Bir":
        show_this_week = weeks_diff % 2 == 0
    elif freq == "Tek Seferlik":
        show_this_week = weeks_diff == 0
    elif "Aylık" in freq:
        # Aylık mantığı: O hafta içinde ilgili gün var mı?
        # "Aylık (Son Pazartesi)" kontrolü
        if "Son Pazartesi" in freq:
            # Bu haftanın günlerini kontrol et
            for i in range(5): # Pzt-Cuma
                current_day = week_start_date + datetime.timedelta(days=i)
                if current_day.weekday() == 0: # Pazartesi
                    last_monday = get_last_monday(current_day.year, current_day.month)
                    if current_day == last_monday:
                        meeting_date_this_week = current_day
                        show_this_week = True
                        break
        else:
            # Standart aylık (Tarih bazlı varsayalım veya şimdilik her ayın ilk haftası gibi)
            show_this_week = True 
            
    if show_this_week:
        # Tarih kontrolü (Bitiş Tarihi ve Başlangıç Tarihi)
        if meeting_date_this_week:
             if meeting_date_this_week > meeting_end_date:
                 return False
             if meeting_date_this_week < meeting_start_date:
                 return False
        return True
        
    return False

def get_mixed_color(attendees, colors):
    """Katılımcıların renklerinin ortalamasını alarak dinamik renk üretir."""
    if not attendees:
        return colors.get("Mixed", {"bg": "#E0E0E0", "border": "#666666"})
        
    bg_r, bg_g, bg_b = 0, 0, 0
    border_r, border_g, border_b = 0, 0, 0
    count = 0
    
    found_any = False
    
    for person in attendees:
        if person in colors:
            found_any = True
            c = colors[person]
            # BG hex to int
            bg = c.get('bg', '#CCCCCC').lstrip('#')
            if len(bg) == 6:
                bg_r += int(bg[0:2], 16)
                bg_g += int(bg[2:4], 16)
                bg_b += int(bg[4:6], 16)
            
            # Border hex to int
            border = c.get('border', '#666666').lstrip('#')
            if len(border) == 6:
                border_r += int(border[0:2], 16)
                border_g += int(border[2:4], 16)
                border_b += int(border[4:6], 16)
            count += 1
            
    if found_any and count > 0:
        new_bg = f"#{int(bg_r/count):02x}{int(bg_g/count):02x}{int(bg_b/count):02x}"
        new_border = f"#{int(border_r/count):02x}{int(border_g/count):02x}{int(border_b/count):02x}"
        return {"bg": new_bg, "border": new_border}
    
    return colors.get("Mixed", {"bg": "#E0E0E0", "border": "#666666"})

def draw_weekly_view(ax, data, week_start_date):
    settings = data['settings']
    days = settings['days']
    colors = settings.get('colors', {})
    
    work_start_min = time_to_min(settings['work_start'])
    work_end_min = time_to_min(settings['work_end'])
    
    # Başlık
    week_end_date = week_start_date + datetime.timedelta(days=4)
    header_text = f"{week_start_date.day} {TR_MONTHS[week_start_date.month]} - {week_end_date.day} {TR_MONTHS[week_end_date.month]} {week_start_date.year}"
    
    # Sayfa düzeni ayarları (Margins)
    plt.subplots_adjust(top=0.85, bottom=0.15, left=0.05, right=0.95)

    # Başlığı biraz daha yukarı al (boşluk artırma)
    # Veri koordinatlarında çiziyoruz. Eksenin üstü work_start_min.
    # 80 birim yukarı alalım.
    ax.text(len(days)/2, work_start_min - 80, header_text, ha='center', va='center', fontsize=20, fontweight='bold', color='#333333')

    # Eksen Ayarları
    ax.set_ylim(work_end_min, work_start_min)
    ax.set_xlim(0, len(days))
    ax.set_facecolor("#FFFFFF")
    
    # Grid
    grid_color = "#E0E0E0"
    for i in range(len(days) + 1):
        ax.axvline(i, color=grid_color, linestyle='-', linewidth=1)
    
    current_time = work_start_min
    while current_time <= work_end_min:
        ax.axhline(current_time, color=grid_color, linestyle='--', linewidth=0.5, alpha=0.5)
        current_time += 30
        
    # Gün Başlıkları
    for i, day in enumerate(days):
        # O günün tarihi
        current_day = week_start_date + datetime.timedelta(days=i)
        day_label = f"{day}\n{current_day.day} {TR_MONTHS[current_day.month]}"
        # Gün başlıklarını ızgaradan biraz uzaklaştır
        ax.text(i + 0.5, work_start_min - 30, day_label, ha='center', va='center', fontsize=14, fontweight='bold', color='#333333')

    # Y Eksen Etiketleri
    yticks = []
    yticklabels = []
    current_time = work_start_min
    while current_time <= work_end_min:
        yticks.append(current_time)
        h = current_time // 60
        m = current_time % 60
        yticklabels.append(f"{h:02d}:{m:02d}")
        current_time += 60
    ax.set_yticks(yticks)
    ax.set_yticklabels(yticklabels)
    ax.tick_params(axis='y', labelsize=12)
    
    # Öğle Arası
    lunch_start = time_to_min(settings['lunch_break']['start'])
    lunch_end = time_to_min(settings['lunch_break']['end'])
    rect_lunch = patches.Rectangle((0, lunch_start), len(days), lunch_end - lunch_start, linewidth=0, facecolor='#F2F2F2', alpha=0.5)
    ax.add_patch(rect_lunch)
    ax.text(len(days)/2, (lunch_start + lunch_end)/2, "ÖĞLE ARASI", ha='center', va='center', color='#999999', fontsize=10, fontstyle='italic')
    
    # Resmi Tatiller
    holidays = data.get('holidays', {})
    # Listeden sözlüğe geçiş kontrolü (Geriye dönük uyumluluk)
    if isinstance(holidays, list):
        holidays = {h: "RESMİ TATİL" for h in holidays}

    for i, day in enumerate(days):
        current_day = week_start_date + datetime.timedelta(days=i)
        current_day_str = current_day.strftime("%Y-%m-%d")
        if current_day_str in holidays:
            holiday_name = holidays[current_day_str]
            # Tüm günü kapatan blok
            rect_h = patches.Rectangle((i, work_start_min), 1, work_end_min - work_start_min, 
                                     linewidth=0, facecolor='#FFEBEE', alpha=0.85, zorder=25)
            ax.add_patch(rect_h)
            ax.text(i + 0.5, (work_start_min + work_end_min)/2, holiday_name, 
                   ha='center', va='center', rotation=90, fontsize=16, color='#D32F2F', fontweight='bold', zorder=30)

    # Toplantıları Filtrele ve Hazırla
    meetings_by_day = {day: [] for day in days}
    
    for meeting in data['meetings']:
        # Önce bu haftada gösterilecek mi kontrol et
        if not should_show_meeting(meeting, week_start_date):
            continue
            
        day_str = meeting['day'].strip()
        if day_str in days:
            # Tatil kontrolü
            day_idx = days.index(day_str)
            meeting_date = week_start_date + datetime.timedelta(days=day_idx)
            meeting_date_str = meeting_date.strftime("%Y-%m-%d")
            
            # Sözlük/Liste kontrolü
            is_holiday = False
            if isinstance(holidays, dict):
                is_holiday = meeting_date_str in holidays
            else:
                is_holiday = meeting_date_str in holidays
                
            if is_holiday:
                continue # Tatil gününe toplantı koyma
            
            start = time_to_min(meeting['start_time'])
            end = time_to_min(meeting['end_time'])
            meeting['start_min'] = start
            meeting['end_min'] = end
            meetings_by_day[day_str].append(meeting)
            
    # Kişi Bazlı Çakışma Kontrolü (Conflict Detection)
    conflicting_meeting_ids = set()
    for day_str in days:
        day_meetings = meetings_by_day[day_str]
        n = len(day_meetings)
        for i in range(n):
            for j in range(i + 1, n):
                m1 = day_meetings[i]
                m2 = day_meetings[j]
                
                # Zaman Çakışması Kontrolü
                if max(m1['start_min'], m2['start_min']) < min(m1['end_min'], m2['end_min']):
                    # Katılımcı Çakışması Kontrolü
                    attendees1 = set(m1.get('attendees', []))
                    attendees2 = set(m2.get('attendees', []))
                    
                    if not attendees1.isdisjoint(attendees2):
                        conflicting_meeting_ids.add(id(m1))
                        conflicting_meeting_ids.add(id(m2))

    # Çizim ve Çakışma Mantığı
    for day_str in days:
        day_meetings = meetings_by_day[day_str]
        if not day_meetings: continue
        
        day_idx = days.index(day_str)
        day_meetings.sort(key=lambda x: x['start_min'])
        
        # Gruplama Algoritması (Çakışan Grupları Bul)
        groups = []
        if day_meetings:
            current_group = [day_meetings[0]]
            group_end = day_meetings[0]['end_min']
            
            for meeting in day_meetings[1:]:
                if meeting['start_min'] < group_end:
                    current_group.append(meeting)
                    group_end = max(group_end, meeting['end_min'])
                else:
                    groups.append(current_group)
                    current_group = [meeting]
                    group_end = meeting['end_min']
            groups.append(current_group)
        
        # Her grubu çiz
        for group in groups:
            columns = []
            meeting_cols = {}
            
            # 1. Sütun Atama (Packing)
            for meeting in group:
                placed = False
                for i, col_end in enumerate(columns):
                    if meeting['start_min'] >= col_end:
                        columns[i] = meeting['end_min']
                        meeting_cols[id(meeting)] = i
                        placed = True
                        break
                if not placed:
                    columns.append(meeting['end_min'])
                    meeting_cols[id(meeting)] = len(columns) - 1
            
            total_cols = len(columns)
            
            # 2. Genişleme Mantığı (Smart Expansion)
            # Her sütun için kullanım aralıklarını kaydet
            col_usage = {i: [] for i in range(total_cols)}
            for meeting in group:
                c_idx = meeting_cols[id(meeting)]
                col_usage[c_idx].append((meeting['start_min'], meeting['end_min']))
            
            # Her toplantı için genişleme miktarını (span) hesapla
            meeting_spans = {}
            for meeting in group:
                start = meeting['start_min']
                end = meeting['end_min']
                c_idx = meeting_cols[id(meeting)]
                span = 1
                
                # Sağa doğru bak: boşsa genişle
                for check_col in range(c_idx + 1, total_cols):
                    is_free = True
                    for u_start, u_end in col_usage[check_col]:
                        # Çakışma kontrolü (Interval Overlap)
                        if max(start, u_start) < min(end, u_end):
                            is_free = False
                            break
                    if is_free:
                        span += 1
                    else:
                        break # Engellendi, daha öteye gidemez (bitişik olmalı)
                
                meeting_spans[id(meeting)] = span

            base_col_width = 0.9 / total_cols
            
            for meeting in group:
                col_idx = meeting_cols[id(meeting)]
                span = meeting_spans[id(meeting)]
                
                start = meeting['start_min']
                end = meeting['end_min']
                duration = end - start
                
                attendees = meeting.get('attendees', [])
                bg_color = "#DDDDDD"
                border_color = "#666666"
                
                # Renk Belirleme Mantığı
                if set(attendees) == set(["Özden", "Burak", "Doğukan"]):
                    c = colors.get("All Team", {})
                    bg_color = c.get("bg", "#FFCCCC")
                    border_color = c.get("border", "#FF0000")
                elif len(attendees) == 1:
                    person = attendees[0]
                    c = colors.get(person, {})
                    bg_color = c.get("bg", "#E0E0E0")
                    border_color = c.get("border", "#666666")
                else:
                    # Dinamik Karışık Renk
                    c = get_mixed_color(attendees, colors)
                    bg_color = c.get("bg", "#E0E0E0")
                    border_color = c.get("border", "#666666")
                
                linewidth = 2
                # Çakışma Vurgusu
                if id(meeting) in conflicting_meeting_ids:
                    border_color = "#FF0000"
                    linewidth = 5
                     
                # Genişlik hesaplama (span ile)
                final_width = (base_col_width * span) - 0.02
                x_pos = day_idx + 0.05 + (col_idx * base_col_width)
                
                rect = patches.Rectangle((x_pos, start), final_width, duration, linewidth=linewidth, edgecolor=border_color, facecolor=bg_color, joinstyle='round', zorder=10)
                ax.add_patch(rect)
                
                text_x = x_pos + (final_width / 2)
                text_y = start + (duration / 2)
                
                # Metin kaydırma (width'e göre)
                # 1 birim genişlik ~ 40 karakter sığıyorsa, oranlayalım
                # base_col_width tüm günün %90'ı. Tüm gün ~ 40 char?
                # Deneme yanılma: base_col_width=0.9 -> 35 char.
                # Daha güvenli olması için 30 çarpanı kullanalım
                char_limit = int(30 * (final_width / 0.9))
                if char_limit < 8: char_limit = 8
                
                wrapped_title = textwrap.fill(meeting['title'], width=char_limit)
                label = f"{wrapped_title}"
                
                if attendees:
                    attendees_str = ", ".join(attendees)
                    wrapped_attendees = textwrap.fill(attendees_str, width=char_limit)
                    label += f"\n({wrapped_attendees})"
                
                # Font boyutlarını büyüt (Kullanıcı isteği: yaşlı kullanıcı, büyük yazı)
                # Alan darsa küçült - Overlap önlemek için biraz küçültüldü
                if span == total_cols: # Tam genişlik
                    font_size = 14
                elif final_width > 0.4:
                    font_size = 12
                else:
                    font_size = 10
                    
                ax.text(text_x, text_y, label, ha='center', va='center', fontsize=font_size, wrap=True, color='#333333', zorder=15)

    # Lejant
    legend_elements = []
    for key, val in colors.items():
        if key == "Mixed": continue
        legend_elements.append(patches.Patch(facecolor=val['bg'], edgecolor=val['border'], label=val['label']))
    
    # Lejant konumunu en alta al (footer gibi)
    # Axes coordinates: (0,0) sol alt, (1,1) sağ üst.
    # (0.5, -0.12) eksenin %12 altında ortala.
    # subplots_adjust(bottom=0.15) ile altta yer açtık.
    ncol_val = max(1, min(len(legend_elements), 5))
    ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.12),
              ncol=ncol_val, frameon=False, fontsize=12, 
              columnspacing=2.0, handletextpad=0.5)
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False)
    ax.spines['left'].set_visible(False)
    ax.set_xticklabels([])
    ax.tick_params(axis='x', length=0)

def draw_monthly_view(ax, data, year, month):
    ax.set_title(f"{TR_MONTHS[month]} {year}", fontsize=24, pad=20)
    ax.axis('off')
    
    cal = calendar.monthcalendar(year, month)
    
    # Tablo verilerini hazırla
    table_data = []
    # Gün başlıkları
    table_data.append(TR_DAYS)
    
    # Haftalar
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append("")
            else:
                cell_text = f"{day}\n"
                # O günün toplantılarını bul
                current_date = datetime.date(year, month, day)
                day_name = TR_DAYS[current_date.weekday()] # 0-6
                
                # O gün için geçerli toplantılar (sadece hafta içi)
                if current_date.weekday() < 5: 
                    # Bu haftanın başını bul (gösterim mantığı için)
                    week_start = current_date - datetime.timedelta(days=current_date.weekday())
                    
                    count = 0
                    for meeting in data['meetings']:
                        if meeting['day'] == day_name and should_show_meeting(meeting, week_start):
                            count += 1
                    
                    if count > 0:
                        cell_text += f"\n{count} Toplantı"
                
                row.append(cell_text)
        table_data.append(row)
    
    # Tablo Çizimi
    table = ax.table(cellText=table_data, loc='center', cellLoc='center', bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(12)
    
    # Hücre stilleri
    for (i, j), cell in table.get_celld().items():
        if i == 0: # Başlık satırı
            cell.set_text_props(weight='bold', color='white')
            cell.set_facecolor('#4F81BD')
            cell.set_height(0.1)
        else:
            cell.set_height(0.15)
            if j < 5: # Hafta içi
                cell.set_facecolor('#FFFFFF')
            else: # Hafta sonu
                cell.set_facecolor('#F2F2F2')
                
            # Gün numarası bold olsun (basit regex veya split ile yapılabilir ama burada tüm text bold olur)
            # Hücre içeriği karmaşık olduğu için bırakıyoruz.

def validate_data(data):
    if 'settings' not in data:
        raise ValueError("JSON verisinde 'settings' anahtarı eksik!")

def generate_calendar_pdf(json_file='calendar_data.json', output_file='takvim_ciktisi.pdf', user_filter=None, data=None, start_date=None):
    if data is None:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
    # Veri doğrulama
    validate_data(data)
    
    # Kullanıcı Filtreleme
    if user_filter:
        filtered_meetings = []
        for m in data['meetings']:
            # Eğer kullanıcı "Tümü" ise veya toplantı katılımcılarında varsa
            if user_filter in m.get('attendees', []):
                filtered_meetings.append(m)
        
        data['meetings'] = filtered_meetings
        print(f"Filtre uygulandı: {user_filter} ({len(filtered_meetings)} toplantı)")
        
        # Dosya adına kişi ekle
        base, ext = os.path.splitext(output_file)
        output_file = f"{base}_{user_filter}{ext}"

    # Tarih Ayarları
    if start_date is None:
        # Bugünün tarihi
        today = datetime.date.today()
    else:
        today = start_date
    
    # Bu haftanın Pazartesisi
    week_start_date = today - datetime.timedelta(days=today.weekday())
    
    # PDF Oluştur
    with PdfPages(output_file) as pdf:
        # 4 Hafta Döngüsü
        for w in range(4):
            current_week_start = week_start_date + datetime.timedelta(weeks=w)
            
            # Haftalık Görünüm
            fig, ax = plt.subplots(figsize=(16, 10))
            draw_weekly_view(ax, data, current_week_start)
            pdf.savefig(fig)
            plt.close()

    print(f"Takvim oluşturuldu: {output_file}")
    return output_file

def get_weekly_calendar_figure(data, start_date=None, user_filter=None):
    if start_date is None:
        start_date = datetime.date.today()
        
    # Bu haftanın Pazartesisi
    week_start_date = start_date - datetime.timedelta(days=start_date.weekday())
    
    # Veri Filtreleme (Kopya üzerinde)
    data_copy = json.loads(json.dumps(data)) # Deep copy to avoid modifying original data
    
    if user_filter:
        filtered_meetings = []
        for m in data_copy['meetings']:
            if user_filter in m.get('attendees', []):
                filtered_meetings.append(m)
        data_copy['meetings'] = filtered_meetings

    # Figür oluştur
    fig, ax = plt.subplots(figsize=(16, 10))
    draw_weekly_view(ax, data_copy, week_start_date)
    return fig

if __name__ == "__main__":
    generate_calendar_pdf()
