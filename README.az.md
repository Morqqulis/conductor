# Conductor

[🇷🇺 Русский](README.md) | 🇦🇿 Azərbaycanca

**AI-agentlər üçün intizam sistemi.** İstənilən AI-ni (Claude Code, Cursor, Antigravity)
mühəndis metodologiyası ilə işləməyə məcbur edir: işə başlamazdan əvvəl tapşırığı
təsnif etmək, «hazırdır» deməzdən əvvəl nəticəni sübut etmək — və yoxlanılmamış
`git commit`-i fiziki olaraq buraxmır. Öz səhvlərindən öyrənir: hər uğursuzluq
qaydaya çevrilir və bütün gələcək sessiyalara yüklənir.

## Nədən ibarətdir

| Qat | Nə edir |
|---|---|
| **Metodologiya** | Nüvə (dəmir qanunlar, nəticə qapısı + nəticəni əvvəlcədən proqnozlaşdırma) + playbook-lar: debug, araşdırma, icra, orkestrasiya, skeptik, dərslərin həzmi |
| **Kilidlər** | Üçqatlı commit-qapısı: mühit hook-u (Claude Code / Cursor / Antigravity) + repozitorinin öz git hook-ları. Commit yalnız sübut prosesindən sonra yaradılmış təzə, birdəfəlik marker olduqda keçir |
| **Öyrənmə** | Dərslər jurnalı (`~/.claude/conductor/lessons.md`): bütün AI-lər bir fayla yazır, təzə dərslər hər sessiyanın əvvəlində yüklənir, jurnal dolduqda sistem özü onların daimi qaydalara çevrilməsini tələb edir |

Kilidlər özləri quraşdırılır: yeni repozitorilər onlarla doğulur (`git init`/`clone`),
mövcud olanlar agentin ilk commit-ində qorunur.

## Tələblər

- Windows 10/11, PowerShell (`pwsh` və ya daxili), git
- [Claude Code](https://claude.com/claude-code) — quraşdırılıb və daxil olunub
- Cursor və/və ya Google Antigravity — istəyə görə (adapterlər qlobal quraşdırılır)

## Quraşdırma

```powershell
git clone https://github.com/Morqqulis/conductor.git
cd conductor

# 1. Claude Code: nüvə, hook-lar, dərslər jurnalı, qlobal CLAUDE.md (+smoke-test)
pwsh -File install.ps1

# 2. Cursor + Antigravity qlobal + yeni repozitorilər üçün git şablonu
pwsh -File install-global.ps1
```

İstəyə görə — mövcud repozitorilərə kilidlər (yenilər avtomatik alır):

```powershell
# bir layihə
pwsh -File install-git-gate.ps1 -Repo "D:\layihə\yolu"

# kök altındakı bütün layihələr birdən
pwsh -File install-git-gate.ps1 -Sweep "D:\projects"
```

Adapterləri konkret layihəyə qoymaq (qaydalar layihə ilə birlikdə versiyalanacaq):

```powershell
pwsh -File install-cursor.ps1      -Repo "D:\layihə\yolu"
pwsh -File install-antigravity.ps1 -Repo "D:\layihə\yolu"
```

Quraşdırmadan sonra Cursor və Antigravity-ni yenidən başladın (hook konfiqurasiyaları
startda oxunur). Hər quraşdırıcı təkrar işə salınanda təhlükəsizdir və dəyişdirdiyi
hər şeyin ehtiyat nüsxəsini (`*.bak-<vaxt möhürü>`) saxlayır.

## Commit-qapısı necə işləyir

1. AI sübut prosesini icra edir (testlər, linter — çıxışı tam oxuyur).
2. **Ayrıca əmrlə** birdəfəlik marker yaradır:
   `touch "$(git rev-parse --git-path conductor-verified)"`
3. Commit edir. `post-commit` hook-u markeri «yeyir» — növbəti commit-ə öz sübutu
   lazımdır. Markersiz commit təlimatla rədd edilir; `--no-verify` və
   `core.hooksPath` dəyişdirilməsi mühit hook-ları səviyyəsində qadağandır.

## Cavab dili harada dəyişdirilir

«Rus dilində, sadə dildə cavab ver» qaydası üç yerdə yerləşir — lazım olanı
redaktə edin və uyğun quraşdırıcını yenidən işə salın:

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
altındakı repozitorilərdən git-kilidləri və adapterləri də təmizləyir. Dəyişdirilən hər
konfiq ehtiyata alınır; yad hook-lar və qeydlər qorunur (özümüzünkülər sentinellərlə
tanınır); köhnə `*.pre-conductor` hook-larınız yerinə qaytarılır; qlobal `CLAUDE.md`
heç vaxt silinmir. Təkrar işə salmaq təhlükəsizdir.

Hissə-hissə əl ilə geri qaytarma: hər konfiqin yanında `*.bak-<vaxt möhürü>` nüsxələri
var; bir repozitoridən kilid — `.git/hooks/` içindəki dörd fayl; yeni repozitorilər
şablonu — `git config --global --unset init.templateDir`.

## Repozitorinin strukturu

```
runtime/          həqiqət mənbəyi: nüvə, playbook-lar, mühit hook-ları, git hook-ları
adapters/         Cursor və Antigravity üçün qayda paketləri və qapılar
deploy/           qlobal CLAUDE.md
qa/               büdcə/naqillənmə linteri, benchmark ssenariləri
docs/             deploy jurnalı ilə spesifikasiya, daşınabilirlik planı
install*.ps1      quraşdırıcılar (yuxarıda)
```

Dəyişikliklər yalnız `runtime/` və `adapters/` içində edilir, sonra `qa\lint.ps1`
və quraşdırıcı: repozitori — həqiqət mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
