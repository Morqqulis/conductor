# Conductor

[![ci](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml)

[🇷🇺 Русский](README.md) | 🇦🇿 Azərbaycanca | [🇬🇧 English](README.en.md)

## Bu nədir

Conductor proqram yazan süni intellekt köməkçiləri üçün qaydalar toplusudur: Claude Code,
Cursor, Antigravity və Codex. Qaydalar köməkçidən diqqətli mühəndis kimi işləməyi istəyir:

- əvvəlcə tapşırığın nə olduğunu və nə qədər riskli olduğunu anlamaq;
- səhvin əlamətini gizlətmək yox, əsl səbəbini tapmaq;
- nəticə yoxlanmamış «hazırdır» deməmək və nə ilə yoxlandığını göstərmək;
- hər şeyi sadə sözlərlə, izahsız terminlər olmadan izah etmək;
- öz səhvlərini yadda saxlamaq və növbəti tapşırıqlarda nəzərə almaq.

Claude Code-da qaydalar hər söhbətin əvvəlində və hər mesajınıza qısa xatırlatma kimi
avtomatik verilir. Digər köməkçilər onları mətn faylı kimi alır.

## İşdə necə görünür

Siz yazırsınız: «Proqramın yoxlamaları `toFixed is not a function` xətası ilə düşür, düzəlt».
Köməkçi əvvəlcə xətanı təkrarlayır və səbəbini tapır, sonra düzəldir və hesabat verir.
Aşağıda test tapşırığından alınmış real cavabın qısaldılmış tərcüməsi var:

> Xətanı düzəltdim: proqramın hər iki yoxlaması indi keçir, əvvəl heç biri keçmirdi.
>
> **Səbəb.** `parsePrice` (`"$12.50"` kimi qiyməti oxuyan hissə) yalnız `$` işarəsini
> silirdi və qiymət mətn olaraq qalırdı. Ona görə qiymətlər toplanmır, hərflər kimi
> yan-yana yazılırdı: 15.5 əvəzinə `'012.503.00'` alınırdı.
>
> **Nəyi dəyişdim.** Yalnız `src/parsePrice.js` faylını: indi o, əsl rəqəm qaytarır,
> yanlış qiymətdə isə aydın mesajla dayanır.
>
> Status: DONE (hər şey edilib və yoxlanılıb)

## Kompüterə nə quraşdırılır

Standart quraşdırma layihələri deyil, yalnız istifadəçi profilinizi dəyişir:

| Nə | Harada | Nə üçün |
|---|---|---|
| Dəyərlər faylı | `~/.claude/CLAUDE.md` | keyfiyyət və sadə dil üçün ümumi qaydalar |
| Qaydalar və köməkçi proqramlar | `~/.claude/conductor/` | əsas qaydalar, dərs yaddaşı, dil seçimi |
| Claude Code ilə əlaqə | `~/.claude/settings.json` | qaydaları söhbətə ötürən beş kiçik proqram |
| Codex və Antigravity üçün qaydalar | `~/.codex/AGENTS.md`, `~/.gemini/AGENTS.md` | həmin köməkçilər üçün eyni qaydalar |
| `conductor` əmri | `~/.local/bin/` | quraşdırma, yoxlama, yeniləmə və silmə |
| Ehtiyat nüsxələr | `~/.local/state/conductor/` | nasazlıqdan sonra əvvəlki vəziyyətə qayıtmaq |
| Əlavə alətlər | `~/.local/share/conductor-companions/` və terminalın başlanğıc faylında bir sətir | RTK (əmrlərin çıxışını qısaldır) və Graphify (layihə xəritəsi); istəyə bağlı |

Cursor üçün qayda hazırlanır, amma əl ilə aktivləşdirilir. `--skip-companions` əlavə
alətlərdən imtina edir, `--skip-global-md` şəxsi `CLAUDE.md` faylınızı saxlayır.

**Sessiya mühitinin qorunması.** Köməkçinin Bash-da (əmr sətrində) işə saldığı hər əmrin
əvvəlinə Claude Code söhbətin xidməti fayllarını
`~/.claude/session-env/<sessiya>/(setup|sessionstart|cwdchanged|filechanged)-hook-N.sh` əlavə edir.
Codex kimi plaginlər hər söhbətin başlanğıcında ora öz sətirlərini yazır. Mətn təxminən 8 KB-dan
böyük olanda Git for Windows Bash əmrləri kəsir və hər biri «unexpected EOF» xətası ilə dayanır.
Hər başlanğıcda Conductor cari söhbətin bu fayllarında təkrarlanan sətirləri silir — yalnız
hamısı sadə `AD=dəyər` sətirlərindən ibarət olduqda, əks halda heç nəyə toxunmur — və mətn yenə
də 6 KB-dan böyükdürsə, xəbərdarlıq edir. Görülən iş `~/.claude/conductor/session-env.log`
faylına yazılır; Conductor silinəndə bu jurnal hətta `--remove-lessons` ilə də qalır, lazım olsa
`session-env.log*` fayllarını əl ilə silin.

## Bu neçəyə başa gəlir

Qaydalar köməkçinin oxuduğu mətndir, oxunan mətn isə planınızın limitlərindən istifadə edir.

| Nə vaxt | Nə qədər mətn |
|---|---|
| Söhbətin əvvəli | təxminən 10 KB qayda və 3 KB-a qədər dərs yaddaşı göstəricisi |
| Hər mesajınız | təxminən 0,4 KB xatırlatma |
| Əsas köməkçinin işə saldığı hər köməkçi | təxminən 3 KB |

2026-cı ilin avqustunda qısa tapşırıqda ölçmə köməkçinin təxminən iki əlavə addımı və
təxminən 0,23 dollar əlavə xərc göstərdi. Uzun söhbətlərdə qaydaların payı kiçikdir.

## Nə sübut olunub, nə olunmayıb

- **Sübut olunub:** Conductor ilə köməkçi xətanı düzəltməzdən əvvəl 12 haldan 12-də
  təkrarladı, onsuz 12-dən 0-da ([hesabat](qa/reports/ab-report-v2.md)).
- **Sübut olunub:** sadə dil qaydası cavabdakı izahsız terminləri təxminən dörd dəfə,
  13-dən 4-ə qədər azaltdı ([hesabat](qa/reports/plain-language-2026-11-04.md)).
- **Sübut olunmayıb:** Conductor-un real layihələrdə uzun söhbətlərdə kömək etdiyi.
  Test tapşırıqları qısadır və onlarda Conductor-suz, amma dəyərlər faylı olan köməkçi
  eyni dərəcədə yaxşı işlədi.

## Vacib: dəyərlər faylı mütləqdir

Ölçmələrdə yaxşı davranışın əsas hissəsini quraşdırıcının `~/.claude/CLAUDE.md` yerinə
qoyduğu [`deploy/global-CLAUDE.md`](deploy/global-CLAUDE.md) dəyərlər faylı verirdi.
Onsuz Conductor qaydaları dayağını itirir və bunu heç nə bildirməz. Buna görə Conductor-un
silinməsi bu faylı qəsdən saxlayır. Ölçmənin ilkin şərtləri:
[`qa/reports/baseline-values-file.md`](qa/reports/baseline-values-file.md), nəticələr:
[`qa/reports/baseline.md`](qa/reports/baseline.md).

Hər şeyin quraşdırıldığını və işlədiyini `conductor doctor` əmri yoxlayır.

## Tələblər

- `bash`, `git`, Python 3.10+ (quraşdırıcılara — onlar başqa alətlərə məxsus JSON
  konfiqlərini redaktə edir — və icra zamanı test icraları jurnalına lazımdır: python
  olmadan jurnal səssizcə heç nə yazmır, qalan hook-lar işləyir)
- Windows: Git Bash daxil olan Git for Windows; adi PowerShell-dən başlatmaq olar.
  Windows və Linux CI-də yoxlanılır; macOS ayrıca yoxlanılmayıb
- [Claude Code](https://claude.com/claude-code) — quraşdırılıb və daxil olunub
- Cursor, Google Antigravity və/və ya OpenAI Codex — istəyə görə (adapterlər qlobal quraşdırılır)

## Quraşdırma

**Bir qlobal quraşdırıcı, klonlama tələb olunmur.** Rəsmi mənbə arxivini müvəqqəti
qovluğa yükləyir, Conductor-u Claude Code, Codex və Antigravity üçün quraşdırır,
Cursor qaydasını hazırlayır, həmçinin Superpowers, RTK və Graphify-ni quraşdırır.

Windows, PowerShell:

```powershell
& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/Morqqulis/conductor/main/install.ps1')))
```

Linux/macOS və ya Git Bash:

```bash
set -o pipefail; curl -fsSL https://raw.githubusercontent.com/Morqqulis/conductor/main/bootstrap.sh | bash
```

Bu əmrlər rəsmi repozitoriyanın kodunu icra edir. Əvvəlcə yoxlamaq istəyirsinizsə,
skripti yükləyin, oxuyun və yerli başladın. Git əvvəlcədən quraşdırılmalıdır; yükləyici
Git və Python-u soruşmadan quraşdırmır və sistemin təhlükəsizlik siyasətini dəyişmir.
Windows-da Python 3.10+ tapılmasa, quraşdırıcı onu qurmağı təklif edir: yalnız `y` və ya
`yes` cavabından sonra `winget`-i işə salır, Microsoft Store mənbəyindən rəsmi Python
quraşdırma menecerini qurur (paketin və mənbənin şərtlərini sizin adınızdan qəbul edərək) və
onun vasitəsilə istifadəçi hesabınız üçün menecerin standart olaraq qurduğu (son stabil)
Python versiyasını quraşdırır. Menecer artıq varsa, `winget` işə salınmır. Hər hansı başqa
cavab, oxunması mümkün olmayan cavab və ya həm menecerin, həm də `winget`-in olmaması halında
Python quraşdırılmır və quraşdırıcı onu özünüz necə quraşdıracağınızı izah edir.
Rus, ingilis və ya Azərbaycan dilini seçin. Terminal yoxdursa, saxlanmış dil,
o da yoxdursa rus dili istifadə olunur. PowerShell-də `-Language az` əlavə edin
və ya konveyerin son `bash` əmrini `bash -s -- --language az` ilə əvəz edin.
`--ref vX.Y.Z` və ya tam commit (PowerShell: `-Ref`) versiyanı sabitləyir: yükləyicinin ikinci
mərhələsi də, quraşdırılan fayllar da ondan götürülür. Yanlış dəyər yükləmədən əvvəl rədd edilir.
Kodlar: `ru` — rus dili, `en` — ingilis dili, `az` — Azərbaycan dili.
Quraşdırıcı qlobal `~/.claude/CLAUDE.md` faylını dəyərlər faylı ilə əvəz edir (əvvəlki fayl
snapshot-da saxlanılır); `--skip-global-md` (PowerShell: `-SkipGlobalMd`) şəxsi faylınızı
saxlayır. `--skip-companions` (`-SkipCompanions`) Superpowers, RTK və Graphify quraşdırmır.

Artıq yüklənmiş mənbə qovluğunda **yalnız** `bash install.sh` kifayətdir.
`--scope claude` Claude Code-u, `--scope global` digər qlobal adapterləri seçir;
standart seçim `all`-dır. PowerShell-də `-Scope claude/global/all` istifadə olunur.
`install-global.sh` daxili/uyğunluq addımı kimi qalır, onu ayrıca başlatmaq lazım deyil.
Cursor qaydasını əvvəlki kimi əl ilə aktivləşdirmək lazımdır; quraşdırıcı yolunu göstərir.

İlk quraşdırma mövcud qlobal qayda faylını əvəz etməzdən əvvəl xəbərdarlıq edir və
`~/.local/state/conductor/updates/<id>/` altında bərpa olunan nüsxə saxlayır.
Qeydiyyatlı fayllardakı şəxsi dəyişikliklər təkrar quraşdırmanı dayandırır.
Yad proqramlar və əmrlər əvəz edilmir. Dərslər, layihə yaddaşı və yad parametrlər qorunur.

### macOS: yeniləmədə «linked destination is not allowed»

4 noyabr 2026-dan köhnə quraşdırmalar macOS-da özlərini yeniləyə bilmir: macOS-un müvəqqəti
qovluğu keçid arxasındadır (`/var` -> `/private/var`), köhnə yeniləyici isə belə yolları rədd
edir. Bir dəfə müvəqqəti qovluğun həqiqi yolu ilə yeniləyin; sonra `conductor update` adi
qaydada işləyir:

```bash
TMPDIR="$(cd "${TMPDIR:-/tmp}" && pwd -P)" conductor update
```

### Claude Code bulud sessiyaları (claude.ai/code)

Bulud sessiyası quraşdırma olmayan təzə konteynerdə işləyir. Bu sətri bulud mühitinin
**quraşdırma skriptinə** bir dəfə əlavə edin (sessiya başlığındakı mühit menyusu → Edit →
Setup script):

```bash
(set -o pipefail; curl -fsSL https://raw.githubusercontent.com/Morqqulis/conductor/main/bootstrap.sh | bash -s -- --language az --skip-companions) || echo "Conductor: quraşdırma alınmadı; sessiya onsuz davam edir"
```

Bundan sonra həmin mühitin hər yeni bulud sessiyası Conductor ilə başlayır, heç bir əmr
lazım deyil. Quraşdırma bir neçə saniyə çəkir; `--skip-companions` sürətli start üçün RTK və
Graphify-ı qoymur.

Bulud quraşdırma skriptini hər sessiyada işlətmir: nəticə saxlanılır və təkrar istifadə
olunur (Claude Code sənədlərinə görə — təxminən bir həftə və ya skript dəyişənədək).
Versiyanın geri qalmaması üçün yeni bulud sessiyası əsas qaydalar daxil edilməzdən əvvəl
Conductor-u özü cari `main` versiyasına yeniləyir: adi `conductor update --skip-companions`,
5 saniyədən sonra kəsilir və daha 2 saniyədən sonra məcburi dayandırılır (ölçmə — təxminən
2 saniyə). Yeniləmə alınmasa və ya vaxtı çatmasa, sessiya quraşdırılmış versiya ilə başlayır
(yazı ortasında məcburi dayandırılmış yeniləməni növbəti `conductor update` geri qaytarır);
cəhd adətən Conductor qovluğundakı `cloud-update.log` faylına bir sətir yazır. Bu yalnız
`CLAUDE_CODE_REMOTE=true` təyin olunan yerdə (Claude Code bulud sessiyası onu özü təyin
edir) və yalnız yeni sessiya başlayanda baş verir; yerli quraşdırmalar heç vaxt avtomatik
yenilənmir — yalnız `conductor update` əmrini və ya quraşdırıcını özünüz işə saldıqda.
Söndürmək üçün bulud mühitinin dəyişənlərində `CONDUCTOR_AUTO_UPDATE=0` təyin edin. Quraşdırma
skriptiniz `--ref` ilə versiyanı sabitləyirsə, onu söndürün: əks halda avtomatik yeniləmə
sessiyanı `main` versiyasına keçirir.

Bir neçə agent eyni plan üzrə işləyəndə layihədə iş xəritəsi olur:
`.conductor/work-map.md` (onu agent özü yaradır, git-ə düşmür). Xəritədə yalnız plan yazılır;
kimin nəyi başladığını, təhvil verdiyini və nəyin qəbul edildiyini `evidence/plan.py`
proqramı git-dən oxuyur və planla faktlar arasındakı hər uyğunsuzluğu adlandırır. Xəritə
faylı mövcud olduqca hər mesajınıza bu vəziyyəti göstərən bir sətir əlavə olunur (3 saniyəyə
qədər; istənilən xətada sətir sadəcə əlavə olunmur). Sətri söndürmək üçün
`CONDUCTOR_PLAN_STATUS=0` dəyişənini təyin edin.

### İstənilən qovluqdan quraşdırma, yeniləmə və silinmə

Qlobal əmr `~/.local/bin` daxilindədir (Windows: `conductor.cmd`).
Lazımdırsa, bu qovluğu PATH-a əlavə edin.

```bash
conductor install --language az
conductor status
conductor doctor
conductor update --check
conductor update
conductor uninstall --dry-run
conductor uninstall
```

Bütün əmrlər cari layihənin qaydalarına deyil, istifadəçi profilinə təsir edir.
Python 3.10+, Git və Bash lazımdır. Mənbə rəsmi repozitoridən müvəqqəti qovluğa yüklənir;
`--ref vX.Y.Z` və ya tam commit versiyanı seçir. Saxlanmış dil dəyişmir.
Cursor-un hazırlanmış qaydası yenə əl ilə aktivləşdirilməlidir.
`conductor doctor` heç nəyi dəyişmir: hər quraşdırılmış faylı quraşdırma qeydi ilə yoxlayır,
quraşdırılmış əmrləri və sessiya başlanğıcı hook-unu işə salır, PASS/WARN/FAIL çap edir;
`0` kodu sağlam quraşdırma deməkdir. Repozitoriyanın klonu lazım deyil.

Quraşdırma, yeniləmə, silinmə və geri qaytarma vahid kilid və bərpa mexanizmindən istifadə
edir. Fayllar yazmadan əvvəl və sonra yoxlanır; versiya icra yoxlamalarından sonra yazılır.
Xəta öz dəyişikliklərini geri qaytarır. Qəfil dayanma sonrası növbəti dəyişdirən əmr əvvəlcə
bərpa edir; status yarımçıq əməliyyatı göstərir. Quraşdırılmış CLI özü zədələnibsə, yüklənmiş
quraşdırıcını təkrar başladın. Sonrakı şəxsi dəyişikliklər silinmir, bərpanı dayandırır.
`update --check` quraşdırılmış məlumatları dəyişmir və bərpa etmir.

Nüsxələr şəxsi məlumatdır və silinmədən sonra qalır. Açıq geri qaytarma:
`conductor rollback --backup "GÖSTƏRİLƏN_NÜSXƏ_YOLU"`; silinmədən sonra tam mənbə
nüsxəsindən silənin göstərdiyi Python əmrini işlədin. Windows CLI silinərkən çıxış kodunu
qorumaq üçün nüsxələrin yanında kiçik, məzmununa görə adlandırılmış işəsalma fayllarını saxlayır.
Bütün fayllar eyni anda əvəz edilmir; dəyişiklikdən sonra agent sessiyalarını yenidən başladın.

### Köhnə quraşdırmadan keçid

`conductor status` quraşdırılmış komponentləri göstərirsə, `conductor update` işlədin.
Əmr tapılmırsa, əvvəlcə `~/.local/bin` və PATH-ı yoxlayın. CLI hələ quraşdırılmayıbsa,
yuxarıdakı quraşdırıcını başladın; əvvəlcədən Conductor-u və ya yaddaşını silmək lazım deyil.

Eyni quraşdırıcı `~/.claude/conductor/install-state.json` olmayan köhnə quraşdırmaları,
ilk PowerShell və sonrakı Bash versiyaları daxil olmaqla, avtomatik keçirir. Git tarixçəsini
klonlamaq və ya ayrıca `install-global.sh` işlətmək lazım deyil: köhnə faylların tam
yoxlama cəmləri kataloqu quraşdırıcıya daxildir. Fərqli yer istifadə etmisinizsə, əvvəlki
`CLAUDE_CONFIG_DIR` dəyərini təyin edin; bütün diskdə axtarış aparılmır.

Yazmadan əvvəl bərpa edilə bilən nüsxə yaradılır. Dərslər, kənar parametrlər və əvvəlki
komponentlər saxlanılır; tanınan köhnəlmiş qoşulmalar əvəz edilir. Dil saxlanmış seçimdən
və ya tanınan köhnə qaydalardan götürülür. Seçimlər ziddiyyətlidirsə, dili açıq göstərin:
`--language ru`, `en` və ya `az` (PowerShell: `-Language`). Şəxsi və ya dəyişdirilmiş
`CLAUDE.md` yerində qalır və Conductor-un idarə etdiyi fayl kimi qeydiyyata alınmır.

Keçid məcburi əvəzləmə deyil: dəyişdirilmiş proqram faylları və ya digər agentlərin
köhnə Conductor faylı kimi təsdiqlənməyən qaydaları olduqda əvəzləmə
`unmanaged file would be overwritten` xətası ilə dayanır. Onları əl ilə müqayisə üçün
saxlayın; qorumanı keçmək üçün yaddaşı və qeydiyyatı silməyin. Zədələnmiş qeydiyyat köhnə
quraşdırma hesab edilmir. Keçiddən sonra adi `conductor update` və `conductor uninstall`
işlədin; geri qaytarma göstərilən nüsxə yolu ilə əvvəlki faylları bərpa edir.

### Başqa kompüterə köçürmə və dəyişdirilmiş fayllar

`~/.claude` qovluğu başqa kompüterə kopyalanıbsa, adi quraşdırıcını işə salın: o, Conductor-un
bu qovluqdan kənarda saxladığı faylları (Codex və Antigravity üçün qaydalar, `conductor`
əmri) yenidən qoyur və mövcud olan heç nəyin üzərinə yazmır.
Yeni kompüterdə istifadəçi adı fərqlidirsə, kopyalanmış `settings.json` faylındakı Conductor
hook-ları köhnə qovluğa işarə edir: quraşdırıcı belə köçürməni tanıyır (hook-lar bütövdür və
hamısı eyni əvvəlki qovluğa aparır) və onları yenidən qeydiyyatdan keçirir. Əl ilə
dəyişdirilmiş hook-lara toxunmur və dayanır.

Dəyişdirdiyiniz Conductor faylı quraşdırmanı dayandırır: mesaj onun tam yolunu göstərir. Onu
cari versiya ilə əvəz etmək üçün quraşdırıcını `--replace-modified` (PowerShell:
`-ReplaceModified`) ilə işə salın — sizin versiyanız surət kimi saxlanılır və yolu çap
olunur. Dəyişdirdiyiniz şəxsi `CLAUDE.md` heç vaxt əvəz edilmir: `--skip-global-md` və ya
`--replace-modified` ilə o, olduğu kimi qalır, Conductor onu idarə etməyi dayandırır və
sonrakı quraşdırmalar və yeniləmələr ona toxunmur (Conductor versiyasını qaytarmaq üçün
faylı silin və quraşdırıcını işə salın). `conductor update` özü dəyişdirilmiş faylları əvəz
etmir və çatışmayanları bərpa etmir — dayanır və faylın adını göstərir.

### Birlikdə quraşdırılan alətlər

Conductor quraşdırılması yoxlandıqdan sonra üç alət qoşulur:

- [superpowers](https://github.com/obra/superpowers) — iş prosesi bacarıqları olan Claude
  Code plagini. Rəsmi plagin marketplace-indən quraşdırılır
  (`claude plugin install superpowers@claude-plugins-official --scope user -y`), ehtiyat
  variant — icma marketplace-i `obra/superpowers-marketplace`. Əvvəllər quraşdırıcı onu
  söndürürdü; indi siyasət əksinədir: Conductor prosesin onurğasıdır, superpowers isə
  onun üstündə bacarıqlar verir.
- [rtk](https://github.com/rtk-ai/rtk) — terminal çıxışını sıxaraq token qənaət edən Rust
  proqramı. Quraşdırıcı hazır proqramı rəsmi GitHub relizindən yükləyir və SHA-256 ilə
  yoxlayır; Rust və Cargo lazım deyil. Claude Code bağlantısı (hook, `RTK.md` və ona istinad)
  `rtk init -g --auto-patch` əmri ilə yaradılır.
- [graphify](https://github.com/Graphify-Labs/graphify) — kod bazası üzrə bilik qrafı
  quran alət. PyPI-dakı `graphifyy` paketi mövcud `uv` və ya Python `venv` vasitəsilə ayrıca
  mühitə quraşdırılır; sistemin pip mühiti dəyişmir. Sonra Claude bacarığı qoşulur.
  Digər mühitlərdə bacarığın aktivləşdirilməsi ayrıca aparılır.

Bayraqlar: `--skip-companions` bütün addımı atlayır (CI-nin izolyasiya olunmuş
smoke-testi məhz belə edir); `--no-superpowers` yalnız plagindən imtina edir;
`--keep-superpowers` uyğunluq üçün qəbul edilir və heç nə etmir — plagin onsuz da
quraşdırılır.

Quraşdırma və təkrar quraşdırma RTK/Graphify-nin son sabit versiyalarını yoxlayır:
olmayan alətlər quraşdırılır, Conductor-un idarə etdiyi nüsxələr yenilənir.
`conductor update` Conductor özü aktual olsa da, yalnız mövcud alətləri yeniləyir.
`--check` yalnız versiyaları göstərir; `--skip-companions` bu addımı açıq şəkildə ötürür.
Superpowers avtomatik yenilənmir. Graphify layihə xəritələri yenidən qurulmur.

uv ilə quraşdırılmış Graphify və Cargo ilə quraşdırılmış rəsmi RTK tanındıqda ayrıca,
Conductor-un idarə etdiyi nüsxələrə keçilir. Köhnə proqramlar və menecer məlumatları dəyişmir.
Yeni əmrlər `~/.local/share/conductor-companions/bin` qovluğunda saxlanır və PATH-da köhnə
nüsxələrdən əvvəl gəlir. Sonrakı yeniləmələr yalnız idarə olunan nüsxəni dəyişir.
Naməlum mənşə və ya şəxsi dəyişikliklər olan bağlantı faylları `FAILED` verir və qorunur.
Bu fayllar runtime-dan kənardadır və Conductor silinəndə qalır.
Xarici uv quraşdırmasının qeydini oxumaq üçün Python 3.11+ lazımdır.

Hər alət öz nəticəsini və səbəbini göstərir. Çıxış `0` tələb olunan işin hazır olması,
`1` Conductor xətası, `2` yanlış arqumentlər, `3` Conductor hazır olsa da əlavə alətlərin
hazır olmaması, `130` isə kəsilmə deməkdir. Açıq ötürmə xəta sayılmır.
PATH problemi olduqda lazım olan yol göstərilir. Windows istifadəçi PATH-ını saxlayır;
Linux/Bash digər məzmunu qoruyaraq shell başlanğıc fayllarına kiçik işarələnmiş blok əlavə edir.
Ehtiyat nüsxə yaradılır; geri qaytarma sonrakı şəxsi dəyişiklikləri əvəz etmir. Yeni PATH üçün
yeni terminal açın və tətbiqləri yenidən başladın. Digər shell-lər ayrıca yoxlanmalıdır.
RTK və Graphify bacarığının bağlantısı izolyasiyada hazırlanır və yad parametrlər qorunur.

Adapterləri konkret layihəyə qoymaq (qaydalar layihə ilə birlikdə versiyalanacaq):

```bash
bash install-project.sh --repo "/d/layihə/yolu"
```

Quraşdırmadan sonra yeni qaydanı götürmələri üçün Cursor və Antigravity-ni yenidən başladın
(quraşdırıcı orada öz hook-larını qoymur, yalnız köhnə Conductor qeydlərini silir). Qlobal əməliyyatlar nüsxələri saxlayır; ziddiyyət təkrar quraşdırmanı dayandırır.

## Graphify xəritəsinin təhlükəsiz yenilənməsi

Bu, işçi repozitoridə xəritəyə qulluq üçündür; quraşdırılmış qaydaları yeniləyən
`conductor update` əmrindən ayrıdır. Repozitorinin kökündə, `uv` və Python 3.10+ ilə:

```bash
uv run --with graphifyy==0.9.67 python tools/graphify-update.py --root .
```

`uv` əvəzinə `graphifyy==0.9.67` quraşdırılmış Python 3.10+ mühitində
`python tools/graphify-update.py --root .` işlətmək olar. Yalnız kod dəyişibsə, əmr bütün
kodun AST-sini (sintaksis ağacını) lokal olaraq yenidən qurur, modelə müraciət etmir.

Dəyişmiş sənədlər məna təhlili tələb edir: əmr `NEEDS_SEMANTIC`, `3` çıxış kodu və sorğu
faylının yolunu qaytarır, dərc olunmuş xəritə fayllarını dəyişmir. Cari sessiyanın agenti
Graphify bacarığından istifadə edərək sorğudakı faylları və əvvəlki qrafı oxuyur,
ilkin ID-ləri, kənarları və hiperkənarları (bir neçə düyün arasındakı əlaqələri)
uzlaşdırır, silinmələri mənbə mətninə əsasən izah edir. Sonra eyni əmri
`--semantic FILE --review FILE` ilə təkrar işə salır. Bu giriş faylları təhlil edilən
fayllar toplusundan kənarda və ya `graphify-out/.conductor/` altında olmalıdır.
Faktiki təhlil promptunu saxlayan könüllü `--prompt-file FILE` mənbələrə və prompta bağlı
semantik keşi aktivləşdirir. Yoxlamalar məna təhlilinin tamlığını avtomatik sübut etmir;
bunu agent qiymətləndirməlidir.

Eyni əmr məcburi yoxlamaları tətbiq edir, nəticəni ayrıca qovluqda hazırlayır, mənbələrin
dəyişmədiyini yoxlayır və paralel icralar üçün əməliyyat sisteminin kilidindən istifadə edir.
Xəta zamanı geri qaytarma aparılır; qəfil kəsilmədən sonra növbəti icra yarımçıq dərcetməni
bərpa edir. Sonradan başqasının etdiyi dəyişikliklərlə ziddiyyət bərpanı dayandırır və
məlumatları qoruyur. Qorumaları məcburi keçmək imkanı yoxdur. Xəritəyə yazan adi Graphify
əmrlərini eyni vaxtda işlətməyin.

Uğurlu dərcetməyədək əvvəlki xəritə saxlanır; ehtiyat nüsxələr və aralıq fayllar
`graphify-out/.conductor/` altında yerləşir və Git üçün nəzərdə tutulmayıb. Bütün fayllar
eyni anda dəyişmir, oxuma kilidlənmir: `graph.json` sonuncu əvəz olunur.

## Yoxlama nəticələrinin yaddaşı

Hər iki quraşdırıcı könüllü `conductor/evidence/cli.py` alətini
`${CLAUDE_CONFIG_DIR:-$HOME/.claude}` daxilinə qoyur; Python 3.10+ lazımdır. Alət real
icranı, çıxışı və göstərilən girişlərin vəziyyətini saxlayır. Layihələrin, klonların və
iş nüsxələrinin tarixçələri ayrıdır. Bu, fəaliyyət jurnalı və ya testlərin avtomatik
ötürülməsi deyil. Sadə düymə yazısı dəyişikliyi yenə icra və yeni qeyd tələb etmir.

İcra təsviri JSON-dur; məsələn, `check.py` və `src` olan layihə üçün:

```json
{"schema_version":1,"name":"unit","argv":["python","-B","check.py"],"cwd":".",
 "inputs":["src","check.py"],"environment":[],"external_state":"none_declared",
 "timeout_seconds":60}
```

Təsviri `verification.json` kimi saxlayın; Bash əmrləri:

```bash
EVIDENCE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/conductor/evidence/cli.py"
python "$EVIDENCE" run --project . --spec verification.json
python "$EVIDENCE" list --project .
python "$EVIDENCE" show --project . --id RUN_ID
python "$EVIDENCE" check --project . --id RUN_ID
```

`RUN_ID` yerinə `run`/`list` nəticəsindəki identifikatoru qoyun. `run` həmişə icra edir;
`show` qeydi və tam çıxışın yollarını göstərir. `check` heç nə icra etmir: `MATCH` müşahidə
olunan şərtlərin uyğunluğudur, yeni uğurlu test deyil. Agent girişlərin tamlığını və çıxışın
tətbiq oluna bilməsini yoxlamalıdır; naməlum xarici vəziyyəti `unknown` göstərin. Keçidlər,
oxunmayan girişlər və itmiş mühit açarı `MATCH` vermir; `.git` nəzərə alınmır.
Bütün vacib asılılıqları və sazlamaları göstərin: alət onları özü müəyyən etmir.

Məlumatlar lokaldır: Windows-da `%LOCALAPPDATA%/Conductor/evidence`, digər sistemlərdə
`${XDG_STATE_HOME:-~/.local/state}/conductor/evidence`; mütləq
`CONDUCTOR_EVIDENCE_HOME` yolu bunu dəyişir. Saxlama yeri layihədən kənarda olmalıdır.
Arqumentlər və çıxış sirlər daşıya bilər: onları yayımlamayın; ümumi qovluq məxfiliyi
təmin etmir. Avtomatik təmizləmə və şəbəkəyə göndərmə yoxdur; qaydaların yenidən
quraşdırılması və silinməsi tarixçəni saxlayır. Çıxış həddi 64 MiB-dir; kəsilmiş və ya
zədələnmiş nəticə təkrar istifadəyə əsas vermir. Windows və Linux CI-də yoxlanılır;
digər əməliyyat sistemləri bu alət üçün hələ yoxlanmayıb.

## Commit intizamı

1. AI dəyişikliklərə baxır və yetərli yoxlamanı seçir. Sadə düymə yazısı, şərh və ya
   adi sənəd mətni dəyişəndə test, yığım və brauzer olmadan dəyişikliyə baxmaq kifayətdir.
   Davranış dəyişəndə təsirlənən ssenarilər yoxlanmalıdır.
2. Yoxlanmış fayllar və yoxlamaya aid asılılıqlar, sazlamalar və mühit dəyişməyibsə,
   əvvəlki nəticə qüvvədə qalır. Təkcə yeni mesaj, əlaqəsiz düzəliş və ya commit onu
   etibarsız etmir. Agentin hesabatı, sübutları araşdırılmadan, kifayət deyil.
3. Commit-dən əvvəl AI sübutların commit üçün hazırlanmış dəyişikliklərə uyğunluğunu
   yoxlayır. Hesabatda dəyişikliyə baxış, təkrar istifadə olunan nəticə və yeni icra ayrılır.

Tam test dəsti və yığım yalnız dəyişikliyin təsiri və ya layihənin açıq tələbi əsasında
lazımdır, hər commit və push-dan əvvəl avtomatik deyil. Təsir aydın deyilsə, əvvəl
araşdırılır, sonra zərurət olduqda yoxlama genişləndirilir. Layihənin CI tələbləri
söndürülmür. Yeni versiyanın buraxılışı üçün yığım ayrıca çatdırılma addımıdır.
Bax: [`runtime/playbooks/verification.md`](runtime/playbooks/verification.md).

Bu mətn qaydasıdır, mexaniki kilid deyil: əvvəlki versiyaların marker git-qapısı silinib.
Sahə məlumatları göstərdi ki, o sadəcə lazım deyildi: agentlər onsuz da sübut proseslərini
icra edirdi, kilid isə onların üstünə ayrıca marker faylı yaratmağı tələb edirdi — artıq
görülmüş işə heç nə əlavə etməyən və unudulduqda commit-i sındıran əlavə addım.
Quraşdırıcılar onun qalıqlarını təmizləyir.

## Cavab dili harada dəyişdirilir

Seçim üçün `conductor install --language az` işlədin; lazım olduqda `az` yerinə `ru` və ya
`en` yazın. `Russian`, `English`, `Azerbaijani` tam adları da dəstəklənir. Qısa kodlarda
böyük-kiçik hərf fərqi yoxdur; qaydalar yazılmazdan əvvəl kodlar tam dil adlarına çevrilir.
PowerShell yükləyicisində `-Language az`, Bash quraşdırıcılarında `--language az` işlədin.
Parametr verilmədikdə `install.sh` saxlanmış seçimlə menyu göstərir; Enter onu saxlayır.
Dil parametri olmayan CLI və `conductor update` əvvəlki seçimi saxlayır. Seçim
`~/.claude/conductor/reply-language` faylındadır; `conductor status` ilə yoxlamaq olar.
Layihə üçün `install-project.sh` bu dili götürür; onun `--language` parametri yalnız layihəni dəyişir.
Dili dəyişdikdən sonra agent sessiyalarını yenidən başladın; hazırlanmış Cursor qaydasını əl ilə tətbiq edin.

Dil CLI tərcüməsinə deyil, agentlərin işinə aiddir: əmrlər və parametr adları dəyişmir.
Ortaq qaydalar ingiliscə yazılsa da, agentlərə həm cavablar, həm də görünən düşünmə
(mühit göstərirsə, «thinking») üçün seçilmiş dildən istifadə etməyi açıq bildirir.
Quraşdırma yoxlamaları dil göstərişinin qaydalara çatmasını yoxlayır, hər modelin faktiki
cavablarını deyil. CLI-nin xidməti mesajları ingiliscə qala bilər.

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

Conductor mənbə kodu və şəxsi yaddaş ayrı repozitorilərdədir. Əvvəl bütün şəxsi yaddaş
repozitorisini yeni və ya boş qovluğa bərpa edin, sonra Conductor-u quraşdırın.
`tools/restore-memory.py` tarixçəni, dərsləri, arxivləri, dili və ehtiyat nüsxə skriptini
saxlayır; konkret layihənin yaddaş nüsxəsi ayrıca, açıq əmrlə bərpa edilir.
Dolu təyinat qovluğunun üzərinə yazılmır. Mənbədə commit edilməmiş məlumat clone-a daxil deyil.
Windows cədvəlini ayrıca `tools/schedule-memory-backup.ps1` ilə bərpa edin:
əvvəlcədən baxış var, mövcud tapşırıq əvəz edilmir.
Ardıcıllıq və əmrlər: [yaddaşın bərpası](docs/memory-recovery.md) (rus dilində).

Dərslərə qulluq üçün mənbə kodunun surəti də lazım deyil: quraşdırıcı runtime yanında
`memory/migrate-lessons.sh` yerləşdirir; qayda `playbooks/distill.md` faylındadır.
Sessiyanın əvvəlində son qeydlər deyil, yaddaşın ünvanları verilir. Tapşırıq məlum olduqda
agent Python 3 vasitəsilə mütləq yolla `memory/recall.py --query "tapşırıq terminləri"`
işlədir; lazımi jurnal `--ledger` ilə seçilir. Təlimat: `memory/recall.md`.
Axtarış gələnləri və təsnif edilmiş dərslərin tam mətnini, indeksdə olmayan faylları da oxuyur.
Sözlərə görə namizədlər tapılır; mənanı və tətbiq şərtlərini agent yoxlayır. Sinonimlər və
başqa dildə terminlər əlavə `--query` ilə verilir. Yenilik yalnız uyğunluq bərabər olduqda
üstünlük verir. Uyğunluq yoxdursa, əlaqəsiz yeni dərslər göstərilmir. Oxuma xətaları və
limitin aşılması uğurlu boş nəticə deyil, `PARTIAL` verir. Python yoxdursa, fayllarda birbaşa
axtarış edilir. Yaddaş dəyişmir; yeni baza, xidmət və miqrasiya tələb olunmur.
Dərslərə qulluq qaydaları dəyişməyib; axtarışı hər mesajda təkrarlamaq lazım deyil.
Silmə şəxsi yaddaşı və naməlum faylları standart olaraq saxlayır. Bu, kompüter nasazlığına
qarşı şəxsi repozitorinin ayrıca ehtiyat nüsxəsini əvəz etmir.

## Silinmə

Quraşdırılmış CLI mənbə qovluğu tələb etmir:

```bash
conductor uninstall --dry-run
conductor uninstall
# Bərpa olunan nüsxəni saxlayaraq dərsləri də açıq şəkildə silmək:
conductor uninstall --remove-lessons
```

Mənbədən `bash uninstall.sh` eyni mexanizmi istifadə edir.
Dərslər standart olaraq əvvəlki yerində qalır; `--keep-lessons` bu rejimlə uyğundur.
Şəxsi `CLAUDE.md`, yoxlama nəticələri, RTK, Graphify, Superpowers və layihə qaydaları qalır.
Dəyişmiş idarə olunan fayl və ya manifesti olmayan naməlum quraşdırma silinmədən imtinaya
səbəb olur. Nüsxələr `~/.local/state/conductor/updates/` daxilindədir.
Silinmədən sonra `conductor` mövcud deyil: tam mənbə nüsxəsindən göstərilən bərpa əmrini
istifadə edin. Köhnə ehtiyat nüsxələr avtomatik silinmir.
Yeri açıq şəkildə boşaltmaq olar: `conductor prune --keep 5 --dry-run` nəyin silinəcəyini
göstərir, `--dry-run` olmadan beş ən yeni nüsxədən başqa hamısını silir. Tanınmayan fayl və
qovluqlara toxunulmur.

Könüllü `bash uninstall.sh --sweep-roots "/d/projects,/d/top"` yalnız açıq göstərilən
layihələri də təmizləyir; əvvəlcə `--dry-run` ilə baxın.

Layihə faylları yalnız adına görə silinmir: tam məzmun məlum Conductor versiyasına
uyğun olmalıdır (seçilmiş dil nəzərə alınır). Yad, dəyişdirilmiş və ya naməlum məzmun,
keçidlər və qarışıq qovluqlar saxlanır, təmizləmə imtina bildirir. Məlum layihə
faylları dəyişdirilməzdən əvvəl layihənin `.conductor-project-backups/` qovluğunda
ehtiyat nüsxə yaradılır. Nüsxələrdə şəxsi parametrlər ola bilər; onları Git-ə əlavə etməyin.
`install-project.sh --dry-run --repo <yol>` yazmadan planı göstərir.
Silinmə vahid tranzaksiya deyil: layihədəki imtina artıq yerinə yetirilmiş qlobal
addımları geri qaytarmır. Bu, qlobal tranzaksiyadan kənar ayrıca əməliyyatdır.

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

Quraşdırılan hissənin dəyişiklikləri yalnız onun mənbələrində edilir: `runtime/`,
`adapters/core-body.md` və digest başlıqları `adapters/*/header.*`, `deploy/global-CLAUDE.md`,
quraşdırılan alətlər `tools/settings-json.py` və `tools/migrate-lessons.sh`; sonra
`bash tools/build-digests.sh`, `bash qa/lint.sh` və quraşdırıcı: repozitori — həqiqət
mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
