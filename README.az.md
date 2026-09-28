# Conductor

[![ci](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml/badge.svg)](https://github.com/Morqqulis/conductor/actions/workflows/ci.yml)

[🇷🇺 Русский](README.md) | 🇦🇿 Azərbaycanca | [🇬🇧 English](README.en.md)

**AI-agentlər üçün intizam sistemi.** İstənilən AI-ni (Claude Code, Cursor, Antigravity,
Codex) mühəndis metodologiyası ilə işləməyə məcbur edir: işə başlamazdan əvvəl tapşırığı
təsnif etmək, «hazırdır» deməzdən əvvəl və hər `git commit`-dən əvvəl nəticəni sübut
etmək. Öz səhvlərindən öyrənir: dərslər saxlanır və gələcək sessiyalarda tapşırığa
uyğun seçilir.

## Nədən ibarətdir

| Qat | Nə edir |
|---|---|
| **Metodologiya** | Nüvə (dəmir qanunlar, nəticə qapısı + nəticəni əvvəlcədən proqnozlaşdırma) + playbook-lar: debug, araşdırma, icra, orkestrasiya, skeptik, dərslərin həzmi + metod dispetçeri: tapşırığın mahiyyəti yanaşmanı seçir (nəzarət qrupu, instrumentasiya, variantlar münsifləri…) |
| **Dəyişikliyə uyğun yoxlama** | Yoxlamanın həcmi commit-dən deyil, dəyişiklikdən asılıdır. Sadə düymə yazısı üçün dəyişikliyə baxmaq kifayətdir; davranış dəyişəndə təsirlənən ssenarilər yoxlanır. Uyğun nəticələr təkrar istifadə olunur |
| **Yaddaş** | İki anbar: **gələnlər** (`~/.claude/conductor/lessons.md`) — dərs başına bir sətir, maşındakı bütün AI-lər ora yazır; **təsnif edilmiş** (`~/.claude/conductor/lessons/`) — dərs başına bir fayl və indeks. Claude Code və Codex tapşırığa uyğun yerli axtarışa çıxış alır; agent uyğun qeydləri kontekstdə oxuyur. Yenilik yalnız əlavə meyardır |

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

Sübutun sərhədləri barədə dürüst qeyd. İlk ölçmə (2026-07) faylın **qısaldılmış rusca**,
56 sətirlik nüsxəsi üzərində aparılıb (`qa/reports/baseline-values-file.md`). 2026-08-15
tarixində ölçmə **quraşdırıcının qoyduğu ingiliscə faylın tam mətni üzərində** və modelin
cari nəsli ilə təkrarlanıb ([`qa/reports/ab-report-v2.md`](qa/reports/ab-report-v2.md)):
tam n=5 ilə hər iki qolda 27/27 intizam tələsi — tərcümə intizam minimumunu zəiflətməyib,
Conductor qolu isə 12/12 debug təkrarında baqın düzəlişdən əvvəl reproduksiyasını əlavə
edib, mexanizmin qiyməti isə mülayim qalıb (medianda +2 gediş). Orada da əhatə olunmayan
qalır: uzun sessiyalardakı davranış (tələlər qısadır), `rtk`/üslub/graphify bölmələri —
onlar tələlərdə iştirak etmir — və «3 cəhd» kəsicisi: o, heç bir qolda bir dəfə də işə
düşməyib (ssenari onu induksiya etmir).

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
skripti yükləyin, oxuyun və yerli başladın. Git və Python əvvəlcədən quraşdırılmalıdır;
yükləyici onları səssiz quraşdırmır və sistemin təhlükəsizlik siyasətini dəyişmir.
Rus, ingilis və ya Azərbaycan dilini seçin. Terminal yoxdursa, saxlanmış dil,
o da yoxdursa rus dili istifadə olunur. PowerShell-də `-Language az` əlavə edin
və ya konveyerin son `bash` əmrini `bash -s -- --language az` ilə əvəz edin.
Kodlar: `ru` — rus dili, `en` — ingilis dili, `az` — Azərbaycan dili.

Artıq yüklənmiş mənbə qovluğunda **yalnız** `bash install.sh` kifayətdir.
`--scope claude` Claude Code-u, `--scope global` digər qlobal adapterləri seçir;
standart seçim `all`-dır. PowerShell-də `-Scope claude/global/all` istifadə olunur.
`install-global.sh` daxili/uyğunluq addımı kimi qalır, onu ayrıca başlatmaq lazım deyil.
Cursor qaydasını əvvəlki kimi əl ilə aktivləşdirmək lazımdır; quraşdırıcı yolunu göstərir.

İlk quraşdırma mövcud qlobal qayda faylını əvəz etməzdən əvvəl xəbərdarlıq edir və
`~/.local/state/conductor/updates/<id>/` altında bərpa olunan nüsxə saxlayır.
Qeydiyyatlı fayllardakı şəxsi dəyişikliklər təkrar quraşdırmanı dayandırır.
Yad proqramlar və əmrlər əvəz edilmir. Dərslər, layihə yaddaşı və yad parametrlər qorunur.

### İstənilən qovluqdan quraşdırma, yeniləmə və silinmə

Qlobal əmr `~/.local/bin` daxilindədir (Windows: `conductor.cmd`).
Lazımdırsa, bu qovluğu PATH-a əlavə edin.

```bash
conductor install --language az
conductor status
conductor update --check
conductor update
conductor uninstall --dry-run
conductor uninstall
```

Bütün əmrlər cari layihənin qaydalarına deyil, istifadəçi profilinə təsir edir.
Python 3.10+, Git və Bash lazımdır. Mənbə rəsmi repozitoridən müvəqqəti qovluğa yüklənir;
`--ref vX.Y.Z` və ya tam commit versiyanı seçir. Saxlanmış dil dəyişmir.
Cursor-un hazırlanmış qaydası yenə əl ilə aktivləşdirilməlidir.

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

Quraşdırmadan sonra Cursor və Antigravity-ni yenidən başladın (hook konfiqurasiyaları
startda oxunur). Qlobal əməliyyatlar nüsxələri saxlayır; ziddiyyət təkrar quraşdırmanı dayandırır.

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

Dəyişikliklər yalnız `runtime/` və `adapters/core-body.md` içində edilir, sonra
`bash tools/build-digests.sh`, `bash qa/lint.sh` və quraşdırıcı: repozitori — həqiqət
mənbəyidir, canlı nüsxələr həmişə ondan yığılır.
