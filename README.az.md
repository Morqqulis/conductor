# Conductor

[🇷🇺 Русский](README.md) | 🇦🇿 Azərbaycanca

**AI-agentlər üçün intizam sistemi.** İstənilən AI-ni (Claude Code, Cursor, Antigravity,
Codex) mühəndis metodologiyası ilə işləməyə məcbur edir: işə başlamazdan əvvəl tapşırığı
təsnif etmək, «hazırdır» deməzdən əvvəl və hər `git commit`-dən əvvəl nəticəni sübut
etmək. Öz səhvlərindən öyrənir: hər uğursuzluq qaydaya çevrilir və bütün gələcək
sessiyalara yüklənir.

## Nədən ibarətdir

| Qat | Nə edir |
|---|---|
| **Metodologiya** | Nüvə (dəmir qanunlar, nəticə qapısı + nəticəni əvvəlcədən proqnozlaşdırma) + playbook-lar: debug, araşdırma, icra, orkestrasiya, skeptik, dərslərin həzmi + metod dispetçeri: tapşırığın mahiyyəti yanaşmanı seçir (nəzarət qrupu, instrumentasiya, variantlar münsifləri…) |
| **Commit intizamı** | Commit — hazırlıq bəyanatıdır: hər `git commit`-dən əvvəl təzə sübut prosesi işlədilir və sətirləri cavabda göstərilir. Qayda üç mühitin nüvəsində və digest-lərində yaşayır |
| **Yaddaş** | İki anbar: **gələnlər** (`~/.claude/conductor/lessons.md`) — dərs başına bir sətir, maşındakı bütün AI-lər ora yazır; **təsnif edilmiş** (`~/.claude/conductor/lessons/`) — dərs başına bir fayl və birsətirlik indeks. Sessiya başlayanda gələnlər və indeksin yolu yüklənir; tam indeks lazım olduqda oxunur, ona görə yaddaş böyüdükcə itmir |

## Şərt: dəyərlər faylı məcburidir

**Conductor yalnız qlobal dəyərlər faylı ilə birlikdə işləyir —
[`deploy/global-CLAUDE.md`](deploy/global-CLAUDE.md), quraşdırıcı onu `~/.claude/CLAUDE.md`
ünvanına qoyur. Bu faylı silmək olmaz. Bu, tövsiyə deyil, işləmə şərtidir.**

Sadə dillə, niyə belədir. Sistem iki dəfə yoxlanıldı: Conductor ilə və onsuz. «Onsuz» olan
prosesi intizam üzrə hər 13 sınaqdan keçdi — yoxlanılmamış nəticəni hazır kimi təqdim etmədi,
simptomu yox, səbəbi düzəltdi, saxta «yaşıl işarələr» çəkməkdən imtina etdi və «prod yıxılıb»
təzyiqinə tab gətirdi. Buradan səhv nəticə çıxarmaq asandır: guya model öz-özlüyündə
intizamlıdır.

Belə deyil. Həmin prosesdə Conductor yox idi, **amma dəyərlər faylı yerində idi** və orada
məhz yoxlanılan şeylər yazılıb: «останови и сообщи (статус BLOCKED), а не выдавай черновик
под видом готового», «Проверено: команда + результат», statusların siyahısı və «Факт важнее
настроения: несогласие, давление или похвала — не данные». Davranışı bu mətn göstərdi, boş
model yox. İlkin şərtləri [`qa/reports/baseline-values-file.md`](qa/reports/baseline-values-file.md),
nəticələri isə [`qa/reports/baseline.md`](qa/reports/baseline.md) faylında yoxlamaq olar —
9–11-ci sətirlər (yekun cədvəl) və 36–48 (sətirbəsətir sübutlar).

Praktik məna: əgər bir gün Conductor-dan bu faylı təkrarlayan qaydalar çıxarılsa, sonra kimsə
faylın özünü də silsə, intizam bütövlükdə yox olacaq — özü də bir dənə də xəta mesajı
olmadan. Nə quraşdırıcı, nə linter bunu görməyəcək. `uninstall.sh` qlobal `CLAUDE.md`-i
qəsdən **silmir** — elə buna görə.

Sübutun sərhədləri barədə dürüst qeyd. Ölçmə faylın **qısaldılmış**, 56 sətirlik nüsxəsi
üzərində aparılıb, quraşdırıcı isə 133 sətirlik tam versiyanı qoyur. Onlarda üst-üstə düşən
hissə məhz yuxarıda sitat gətirilən intizam bölmələridir; qalan 77 sətir (`rtk` qaydası,
cavab üslubu haqqında 5.1–5.4 bölmələri, təhlükəsizlik testlərinə genişləndirilmiş tələblər,
graphify quyruğu) heç bir ölçmədə iştirak etməyib. Deməli sübut olunan budur: **intizamı
dəyərlər faylının içindəki sitat gətirilmiş minimum saxlayır.** Faylın qalan hissəsi barədə
məlumat yoxdur — nə lehinə, nə əleyhinə.

## Tələblər

- `bash`, `git`, `python3` (sonuncu yalnız quraşdırıcılara lazımdır — onlar başqa
  alətlərə məxsus JSON konfiqlərini redaktə edir, bunu mətn vasitələri ilə etmək olmaz)
- Windows: git ilə gələn Git Bash kifayətdir. Linux və macOS heç bir qeyd-şərtsiz işləyir
- [Claude Code](https://claude.com/claude-code) — quraşdırılıb və daxil olunub
- Cursor, Google Antigravity və/və ya OpenAI Codex — istəyə görə (adapterlər qlobal quraşdırılır)

## Quraşdırma

```bash
git clone https://github.com/Morqqulis/conductor.git
cd conductor

# 1. Claude Code: nüvə, hook-lar, qlobal CLAUDE.md (+smoke-test)
bash install.sh

# 2. Cursor + Antigravity + Codex qlobal (cavab dilini soruşacaq)
bash install-global.sh
```

Adapterləri konkret layihəyə qoymaq (qaydalar layihə ilə birlikdə versiyalanacaq):

```bash
bash install-project.sh --repo "/d/layihə/yolu"
```

Quraşdırmadan sonra Cursor və Antigravity-ni yenidən başladın (hook konfiqurasiyaları
startda oxunur). Hər quraşdırıcı təkrar işə salınanda təhlükəsizdir və dəyişdirdiyi
hər şeyin ehtiyat nüsxəsini (`*.bak-<vaxt möhürü>`) saxlayır.

## Commit intizamı

1. AI sübut prosesini icra edir (testlər, linter — çıxışı tam oxuyur).
2. Sübut sətirlərini cavabda göstərir.
3. Commit edir. Sübutsuz commit olmamalıdır; uğursuz hook düzəltmək siqnalıdır,
   yan keçmək yox (`--no-verify` — pozuntudur).

Bu mətn qaydasıdır, mexaniki kilid deyil: əvvəlki versiyaların marker git-qapısı silinib.
Sahə məlumatları göstərdi ki, o sadəcə lazım deyildi: agentlər onsuz da sübut proseslərini
icra edirdi, kilid isə onların üstünə ayrıca marker faylı yaratmağı tələb edirdi — artıq
görülmüş işə heç nə əlavə etməyən və unudulduqda commit-i sındıran əlavə addım.
Quraşdırıcılar onun qalıqlarını təmizləyir.

## Cavab dili harada dəyişdirilir

Sadə yol: `install-global.sh`-i yenidən işə salın — dili soruşacaq (və ya birbaşa:
`bash install-global.sh --language Azerbaijani`) və onu bütün mühitlərin qlobal
qaydalarına, o cümlədən Cursor üçün hazır qayda faylına tətbiq edəcək. Rus dilinə
qayıtmaq üçün əvvəlcə `install.sh` (etalonu bərpa edir), sonra `install-global.sh`.

Əl ilə yol — qayda üç yerdə yerləşir, lazım olanı redaktə edin və uyğun
quraşdırıcını yenidən işə salın:

| Mühit | Fayl və bölmə | Redaktədən sonra |
|---|---|---|
| Claude Code, bütün layihələr | [`deploy/global-CLAUDE.md`](deploy/global-CLAUDE.md) → **«5. Язык и стиль ответа»** bölməsi | `bash install.sh` |
| Claude Code, bir layihə | layihə kökündəki `CLAUDE.md` → **«5. Язык и отчёт»** bölməsi | heç nə — dərhal oxunur |
| Cursor, Antigravity və Codex | [`adapters/core-body.md`](adapters/core-body.md) → **«Language and reporting»** bölməsi, sonra `bash tools/build-digests.sh` | `bash install-global.sh` |

Məsələn, Azərbaycan dili üçün həmin bölmələrdə «Answer in Russian» ifadəsini
«Answer in Azerbaijani» ilə əvəz edin (CLAUDE.md-də isə «на русском» →
«на азербайджанском»).

## Başqa kompüterə köçürmə

Repozitori elə distributivin özüdür: klonlayın və yuxarıdakı iki quraşdırıcını
işə salın. Özü köçməyən yeganə şey — toplanmış dərslər jurnalı
`~/.claude/conductor/lessons.md`: sistemin yaddaşını saxlamaq istəyirsinizsə,
bu faylı əl ilə kopyalayın. Həzm olunmuş dərslər artıq playbook-lardadır və
repozitori ilə birlikdə köçəcək.

## Silinmə

Bir əmrlə, əvvəlcədən baxışla:

```bash
# əvvəlcə nəyin silinəcəyinə baxın (heç nəyi dəyişmir)
bash uninstall.sh --dry-run --keep-lessons --sweep-roots "/d/projects,/d/top"

# sonra həqiqətən silin
bash uninstall.sh --keep-lessons --sweep-roots "/d/projects,/d/top"
```

`--keep-lessons` dərslər jurnalını İş masasına saxlayır; `--sweep-roots` göstərilən köklər
altındakı repozitorilərdən köhnə versiyaların adapterlərini və git-kilidlərini təmizləyir.
Dəyişdirilən hər konfiq ehtiyata alınır; yad hook-lar və qeydlər qorunur (özümüzünkülər
sentinellərlə tanınır); qlobal `CLAUDE.md` heç vaxt silinmir. Təkrar işə salmaq
təhlükəsizdir. Hissə-hissə əl ilə geri qaytarma: hər konfiqin yanında
`*.bak-<vaxt möhürü>` nüsxələri var.

## Repozitorinin strukturu

```
runtime/          həqiqət mənbəyi: nüvə, playbook-lar, subagent kontraktı, hook-lar
adapters/         core-body.md — qaydaların ümumi mətni; Cursor/Antigravity digest-ləri
                  ondan yığılır, əl ilə redaktə edilmir
deploy/           qlobal CLAUDE.md
tools/            digest yığımı, JSON konfiqlərin redaktəsi, dərslərin miqrasiyası,
                  köhnə versiyaların git-hook-larının təmizlənməsi
qa/               lint.sh — büdcə, naqillənmə və ifadə linteri;
                  reports/ — nəzarət qrupunun ölçmələri və onunla müqayisə
docs/             deploy jurnalı ilə spesifikasiya, daşınabilirlik planı
install*.sh       quraşdırıcılar, uninstall.sh — silinmə
```

Dəyişikliklər yalnız `runtime/` və `adapters/core-body.md` içində edilir, sonra
`bash tools/build-digests.sh`, `bash qa/lint.sh` və quraşdırıcı: repozitori — həqiqət
mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
