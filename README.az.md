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
| **Dəyişikliyə uyğun yoxlama** | Yoxlamanın həcmi commit-dən deyil, dəyişiklikdən asılıdır. Sadə düymə yazısı üçün dəyişikliyə baxmaq kifayətdir; davranış dəyişəndə təsirlənən ssenarilər yoxlanır. Uyğun nəticələr təkrar istifadə olunur |
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

Əvvəlcədən bilməyə dəyər iki yan təsir. `install.sh` [4/5] addımında üç əlavə alət də
quraşdırır (aşağıya baxın) — əvvəllər o, əksinə, superpowers plaginini söndürürdü; indi
Conductor və superpowers bilərəkdən birlikdə quraşdırılır. `install-global.sh`
`~/.gemini/AGENTS.md` və `~/.codex/AGENTS.md` fayllarını yenidən yazır: orada öz mətniniz
idisə, o, `*.bak-<vaxt möhürü>` nüsxəsində saxlanılır və quraşdırıcı bu barədə ucadan
xəbərdarlıq edir. Quraşdırmanın sağlamlığını istənilən vaxt yoxlamaq:
`bash tools/doctor.sh`.

### Birlikdə quraşdırılan alətlər

Quraşdırmanın [4/5] addımı — ayrıca kök skripti `install-companions.sh` — standart olaraq
üç alət qoyur:

- [superpowers](https://github.com/obra/superpowers) — iş prosesi bacarıqları olan Claude
  Code plagini. Rəsmi plagin marketplace-indən quraşdırılır
  (`claude plugin install superpowers@claude-plugins-official --scope user -y`), ehtiyat
  variant — icma marketplace-i `obra/superpowers-marketplace`. Əvvəllər quraşdırıcı onu
  söndürürdü; indi siyasət əksinədir: Conductor prosesin onurğasıdır, superpowers isə
  onun üstündə bacarıqlar verir.
- [rtk](https://github.com/rtk-ai/rtk) — terminal çıxışını sıxaraq token qənaət edən Rust
  proqramı. Sistemdə cargo varsa,
  `cargo install --git https://github.com/rtk-ai/rtk` ilə quraşdırılır; yoxdursa,
  quraşdırıcı ucadan SKIP sətri çap edir və reliz səhifəsindən hazır binar faylı
  yükləməyi məsləhət görür (doğma Windows dəstəklənir). Bağlantını — Claude Code hook-u və
  `~/.claude/RTK.md` — rtk özü `rtk init -g` əmri ilə qurur; bağlantı yoxdursa, əmr
  avtomatik işə düşür.
- [graphify](https://github.com/Graphify-Labs/graphify) — kod bazası üzrə bilik qrafı
  quran alət. `uv tool install graphifyy` ilə quraşdırılır (paketin adı `graphifyy`, əmr
  isə `graphify`), ehtiyat variant — `pip install graphifyy`; sonra `graphify install`
  `/graphify` bacarığını qeydiyyatdan keçirir, əgər o hələ qeydiyyatda deyilsə.

Bayraqlar: `--skip-companions` bütün addımı atlayır (CI-nin izolyasiya olunmuş
smoke-testi məhz belə edir); `--no-superpowers` yalnız plagindən imtina edir;
`--keep-superpowers` uyğunluq üçün qəbul edilir və heç nə etmir — plagin onsuz da
quraşdırılır.

Hər uğursuzluq ucadan bildirilir və heç vaxt Conductor quraşdırmasını dayandırmır:
quraşdırıla bilməyən alət səbəbi ilə birlikdə SKIP və ya FAIL sətri çap edir, quraşdırma
isə davam edir. Təkrar işə salmaq təhlükəsizdir — artıq qoyulmuş alət üçün «OK already»
yazılır. `uninstall.sh` bu üç aləti silmir: onlar istifadəçi səviyyəsindədir və öz
həyatlarını yaşayır.

Adapterləri konkret layihəyə qoymaq (qaydalar layihə ilə birlikdə versiyalanacaq):

```bash
bash install-project.sh --repo "/d/layihə/yolu"
```

Quraşdırmadan sonra Cursor və Antigravity-ni yenidən başladın (hook konfiqurasiyaları
startda oxunur). Hər quraşdırıcı təkrar işə salınanda təhlükəsizdir və dəyişdirdiyi
hər şeyin ehtiyat nüsxəsini (`*.bak-<vaxt möhürü>`) saxlayır.

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
Sessiyanın əvvəlində yeni dərslər öncə göstərilir; uzun qeydlər olduqda da tam jurnalın
və indeksin ünvanları saxlanır. Bu, bütün yaddaşın yüklənməsi deyil, qısa önbaxışdır.
Silməzdən əvvəl tam ehtiyat nüsxə yaradın: `--keep-lessons` dərsləri saxlayır,
bütün şəxsi repozitorini, tarixçəni, skripti və layihə nüsxələrini deyil.

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
