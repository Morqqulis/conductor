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
| **Öyrənmə** | Dərslər jurnalı (`~/.claude/conductor/lessons.md`): bütün AI-lər bir fayla yazır, təzə dərslər hər sessiyanın əvvəlində yüklənir, jurnal dolduqda sistem özü onların daimi qaydalara çevrilməsini tələb edir |

## Tələblər

- Windows 10/11, PowerShell (`pwsh` və ya daxili), git
- [Claude Code](https://claude.com/claude-code) — quraşdırılıb və daxil olunub
- Cursor, Google Antigravity və/və ya OpenAI Codex — istəyə görə (adapterlər qlobal quraşdırılır)

## Quraşdırma

```powershell
git clone https://github.com/Morqqulis/conductor.git
cd conductor

# 1. Claude Code: nüvə, hook-lar, dərslər jurnalı, qlobal CLAUDE.md (+smoke-test)
pwsh -File install.ps1

# 2. Cursor + Antigravity + Codex qlobal
pwsh -File install-global.ps1
```

Adapterləri konkret layihəyə qoymaq (qaydalar layihə ilə birlikdə versiyalanacaq):

```powershell
pwsh -File install-cursor.ps1      -Repo "D:\layihə\yolu"
pwsh -File install-antigravity.ps1 -Repo "D:\layihə\yolu"
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

Sadə yol: `install-global.ps1`-i yenidən işə salın — dili soruşacaq (və ya birbaşa:
`pwsh -File install-global.ps1 -Language Azerbaijani`) və onu bütün mühitlərin qlobal
qaydalarına, o cümlədən Cursor üçün hazır qayda faylına tətbiq edəcək. Rus dilinə
qayıtmaq üçün əvvəlcə `install.ps1` (etalonu bərpa edir), sonra `install-global.ps1`.

Əl ilə yol — qayda üç yerdə yerləşir, lazım olanı redaktə edin və uyğun
quraşdırıcını yenidən işə salın:

| Mühit | Fayl və bölmə | Redaktədən sonra |
|---|---|---|
| Claude Code, bütün layihələr | [`deploy/global-CLAUDE.md`](deploy/global-CLAUDE.md) → **«5. Язык и стиль ответа»** bölməsi | `pwsh -File install.ps1` |
| Claude Code, bir layihə | layihə kökündəki `CLAUDE.md` → **«5. Язык и отчёт»** bölməsi | heç nə — dərhal oxunur |
| Cursor və Antigravity | [`adapters/cursor/conductor-core.mdc`](adapters/cursor/conductor-core.mdc) və [`adapters/antigravity/conductor-core.md`](adapters/antigravity/conductor-core.md) → **«Language and reporting»** bölməsi | `pwsh -File install-global.ps1` |

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

```powershell
# əvvəlcə nəyin silinəcəyinə baxın (heç nəyi dəyişmir)
pwsh -File uninstall.ps1 -WhatIf -KeepLessons -SweepRoots "D:\projects,D:\top"

# sonra həqiqətən silin
pwsh -File uninstall.ps1 -KeepLessons -SweepRoots "D:\projects,D:\top"
```

`-KeepLessons` dərslər jurnalını İş masasına saxlayır; `-SweepRoots` göstərilən köklər
altındakı repozitorilərdən köhnə versiyaların adapterlərini və git-kilidlərini təmizləyir.
Dəyişdirilən hər konfiq ehtiyata alınır; yad hook-lar və qeydlər qorunur (özümüzünkülər
sentinellərlə tanınır); qlobal `CLAUDE.md` heç vaxt silinmir. Təkrar işə salmaq
təhlükəsizdir. Hissə-hissə əl ilə geri qaytarma: hər konfiqin yanında
`*.bak-<vaxt möhürü>` nüsxələri var.

## Repozitorinin strukturu

```
runtime/          həqiqət mənbəyi: nüvə, playbook-lar, mühit hook-ları
adapters/         Cursor və Antigravity üçün qayda digest-ləri
deploy/           qlobal CLAUDE.md
qa/               büdcə/naqillənmə linteri, benchmark ssenariləri
docs/             deploy jurnalı ilə spesifikasiya, daşınabilirlik planı
install*.ps1      quraşdırıcılar (yuxarıda)
```

Dəyişikliklər yalnız `runtime/` və `adapters/` içində edilir, sonra `qa\lint.ps1`
və quraşdırıcı: repozitori — həqiqət mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
