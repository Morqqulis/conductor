# Conductor

[![ci](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml)

[🇷🇺 Русский](README.md) | 🇦🇿 Azərbaycanca | [🇬🇧 English](README.en.md)

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

Sübutun sərhədləri barədə dürüst qeyd. Ölçmə faylın **qısaldılmış rusca**, 56 sətirlik
nüsxəsi üzərində aparılıb; indi quraşdırıcı 140 sətirlik tam versiyanı qoyur və 2026-08-15
tarixindən bu versiya ingiliscəyə tərcümə olunub (ölçmə vaxtı həmin sətirlər rusca idi —
nüsxə `qa/reports/baseline-values-file.md` faylındadır). Yuxarıda sitat gətirilən intizam
bölmələri quraşdırılan faylda ingiliscə tərcümədə saxlanılıb: ölçülən nüsxə ilə üst-üstə
düşmə artıq hərfi yox, tərcümə səviyyəsindədir və ingiliscə korpusun davranışı ayrıca
ölçülməyib. Qalan 84 sətir (`rtk` qaydası, cavab üslubu haqqında 5.1–5.4 bölmələri,
təhlükəsizlik testlərinə genişləndirilmiş tələblər, graphify quyruğu) heç bir ölçmədə
iştirak etməyib. Deməli sübut olunan budur: **intizamı dəyərlər faylının içindəki sitat
gətirilmiş minimum saxlayır — rusca versiyanın ölçməsinə görə.** Faylın qalan hissəsi və
tərcümə barədə məlumat yoxdur — nə lehinə, nə əleyhinə.

## Tələblər

- `bash`, `git`, `python3` (quraşdırıcılara — onlar başqa alətlərə məxsus JSON
  konfiqlərini redaktə edir — və icra zamanı test icraları jurnalına lazımdır: python
  olmadan jurnal səssizcə heç nə yazmır, qalan hook-lar işləyir)
- Windows: git ilə gələn Git Bash kifayətdir. Linux və macOS heç bir qeyd-şərtsiz işləyir
- [Claude Code](https://claude.com/claude-code) — quraşdırılıb və daxil olunub
- Cursor, Google Antigravity və/və ya OpenAI Codex — istəyə görə (adapterlər qlobal quraşdırılır)

## Quraşdırma

```bash
git clone https://github.com/Morqqulis/conductor.git
cd conductor

# 1. Claude Code: nüvə, hook-lar, qlobal CLAUDE.md (+smoke-test; cavab dilini soruşacaq)
bash install.sh

# 2. Cursor + Antigravity + Codex qlobal (yadda saxlanmış dili təklif edəcək)
bash install-global.sh
```

Əvvəlcədən bilməyə dəyər iki yan təsir. `install.sh` superpowers plaginini söndürür —
iki proses sistemi bir-biri ilə ziddiyyət təşkil edir (saxlamaq üçün:
`--keep-superpowers`). `install-global.sh` `~/.gemini/AGENTS.md` və `~/.codex/AGENTS.md`
fayllarını yenidən yazır: orada öz mətniniz idisə, o, `*.bak-<vaxt möhürü>` nüsxəsində
saxlanılır və quraşdırıcı bu barədə ucadan xəbərdarlıq edir. Quraşdırmanın sağlamlığını
istənilən vaxt yoxlamaq: `bash tools/doctor.sh`.

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
3. Commit edir. Sübutsuz commit olmamalıdır.

Bu mətn qaydasıdır, mexaniki kilid deyil: əvvəlki versiyaların marker git-qapısı silinib.
Sahə məlumatları göstərdi ki, o sadəcə lazım deyildi: agentlər onsuz da sübut proseslərini
icra edirdi, kilid isə onların üstünə ayrıca marker faylı yaratmağı tələb edirdi — artıq
görülmüş işə heç nə əlavə etməyən və unudulduqda commit-i sındıran əlavə addım.
Quraşdırıcılar onun qalıqlarını təmizləyir.

## Cavab dili harada dəyişdirilir

Dil birbaşa terminalda seçilir: həm `install.sh`, həm də `install-global.sh` hər işə
salınanda menyu göstərir və əvvəlki seçim artıq standart cavab kimi təklif olunur —
Enter basmaq kifayətdir, bayraqlara ehtiyac yoxdur. Dili istənilən istiqamətdə (rus
dilinə geri qayıtmaq daxil) dəyişmək üçün quraşdırıcını yenidən işə salıb menyudan
seçin. Seçim `~/.claude/conductor/reply-language` faylında saxlanılır, ona görə
təkrar işə salınmalar heç nəyi sıfırlamır. Claude Code-u hər iki quraşdırıcı
yeniləyir, Cursor, Antigravity və Codex qaydalarını `install-global.sh` yığır;
layihə adapterləri (`install-project.sh`) yadda saxlanmış seçimi səssiz tətbiq edir.
Skriptlər və qeyri-interaktiv işə salınmalar üçün `--language <ad>` var — sualı ötürür.

Qaydaların özü qəsdən bütövlükdə ingiliscə yazılıb. Səbəb: model təlimatlarının
yazıldığı dildə düşünür və rusca qaydalar korpusu, cavab dili başqa seçiləndə belə,
görünən düşünməni rus dilinə çəkirdi. Seçilmiş dildə həm cavablar, həm də görünən
düşünmə («thinking» bloku) aparılır — düşünmə dilini qaydalardakı ayrıca açıq sətir
təyin edir və lint onun mövcudluğunu yoxlayır.

Qayda fayllarında dil bir ifadədir: «Answer in Russian» — quraşdırıcılar kopyalayarkən
orada dilin adını əvəz edir. Repozitoridəki etalonlarda bu ifadəni əl ilə dəyişmək
olmaz: lint tokeni tələb edir (`qa/lint.sh`), belə redaktədən sonra isə ifadə üzrə
əvəzləmə dəyişəcək yer tapmır və `--language` artıq dili çevirmir. Əl ilə yol ikidir,
hər ikisi lokaldır:

| Nə | Necə |
|---|---|
| Claude Code-da bir layihənin dili | layihə kökündəki `CLAUDE.md`-i redaktə edin — dil sətri oradadır və dərhal oxunur |
| Bir layihənin adapterlərinin dili | `bash install-project.sh --repo <yol> --language <ad>` — yalnız bu layihəni dəyişir, maşın seçiminə toxunmur |

## Başqa kompüterə köçürmə

Repozitori elə distributivin özüdür: klonlayın və yuxarıdakı iki quraşdırıcını
işə salın. Özü köçməyən sistemin yaddaşıdır — o, maşında, iki yerdə yaşayır:
gələnlər jurnalı `~/.claude/conductor/lessons.md` və təsnif edilmiş anbar
`~/.claude/conductor/lessons/` (dərs başına bir fayl və indeks). Toplanmış dərsləri
saxlamaq istəyirsinizsə, hər ikisini kopyalayın. Cavab dili seçimini
(`~/.claude/conductor/reply-language`) kopyalamağa ehtiyac yoxdur — təzə quraşdırma
onu sadəcə yenidən soruşacaq.

## Silinmə

Bir əmrlə, əvvəlcədən baxışla:

```bash
# əvvəlcə nəyin silinəcəyinə baxın (heç nəyi dəyişmir)
bash uninstall.sh --dry-run --keep-lessons --sweep-roots "/d/projects,/d/top"

# sonra həqiqətən silin
bash uninstall.sh --keep-lessons --sweep-roots "/d/projects,/d/top"
```

`--keep-lessons` yaddaşın hər iki hissəsini — gələnlər jurnalını və təsnif edilmiş
dərslər anbarını — İş masasına saxlayır; `--sweep-roots` göstərilən köklər
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
                  doctor.sh — quraşdırmanın sağlamlıq yoxlaması, journal-report.sh —
                  test icraları jurnalının oxunması, köhnə versiyaların
                  git-hook-larının təmizlənməsi
qa/               lint.sh — büdcə, naqillənmə və ifadə linteri; lint-selftest.sh —
                  lintin neqativ özünütesti; settings-json-test.py — konfiq
                  redaktəsinin testləri; reports/ — nəzarət qrupunun ölçmələri və
                  onunla müqayisə
docs/             deploy jurnalı ilə spesifikasiya, daşınabilirlik planı
install*.sh       quraşdırıcılar, uninstall.sh — silinmə
```

Dəyişikliklər yalnız `runtime/` və `adapters/core-body.md` içində edilir, sonra
`bash tools/build-digests.sh`, `bash qa/lint.sh` və quraşdırıcı: repozitori — həqiqət
mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
