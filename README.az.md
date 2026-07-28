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

Bu mətn qaydasıdır, mexaniki kilid deyil: əvvəlki versiyaların marker git-qapısı
silinib — sahə məlumatları göstərdi ki, agentlər onu ritual kimi yerinə yetirirdi
(sübutsuz fayl yaradırdı) və mexanika yalnız müdafiəni imitasiya edirdi.
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
qa/               büdcə/naqillənmə linteri, benchmark ssenariləri, tələlər
docs/             deploy jurnalı ilə spesifikasiya, daşınabilirlik planı
install*.sh       quraşdırıcılar, uninstall.sh — silinmə
```

Dəyişikliklər yalnız `runtime/` və `adapters/core-body.md` içində edilir, sonra
`bash tools/build-digests.sh`, `bash qa/lint.sh` və quraşdırıcı: repozitori — həqiqət
mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
