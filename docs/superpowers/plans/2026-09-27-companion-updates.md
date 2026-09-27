# RTK and Graphify Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При установке получать актуальные RTK/Graphify, при update обновлять имеющиеся
копии, не теряя рабочие версии/настройки и не показывая ложный успех.

**Architecture:** Отдельные обнаружение происхождения, получение стабильной версии и
проверяемое применение. Данные companions живут вне удаляемого Conductor; CLI вызывает
координатор после собственной транзакции. Старый shell-вход использует тот же координатор.

**Tech Stack:** Python 3.10+ standard library, существующие Bash, uv/venv и официальный
RTK release downloader; unittest. Новые обязательные пакетные менеджеры не добавлять.

**Spec:** [Общий контракт](../specs/2026-09-27-installation-lifecycle-design.md).
Интеграция CLI — [задача 4 lifecycle](2026-09-27-global-cli-lifecycle.md).
Статус реализации 2026-09-27: обнаружение, отдельные управляемые копии, координатор,
переключение PATH и восстановление реализованы. Согласованный переход uv/Cargo
не меняет исходные хранилища менеджеров. Новые команды живут в `root/bin`, прежние
управляемые назначения `.local/bin` совместимы. Неизвестное происхождение отклоняется.
Проверены реальные RTK 0.42.4 → 0.50.0 и Graphify 0.9.67 → 0.9.69 на Windows/Linux
в отдельных профилях; повторный check сохраняет файлы и подтверждает CURRENT.
Общие тесты companions: 115; Windows/Linux используют свои платформенные сценарии.
Код — `3ce180a`; живая установка пользователя также обновлена до этих версий.
Выбор новых команд проверен, прежние uv/Cargo-файлы сохранились побайтово.
Сбой подключения откатывает только текущий инструмент; незавершённая группа файлов
восстанавливается при следующем запуске. Отдельная проверка отключением защиты:
PASS → assertion FAIL → PASS. Контекст поставки — в HANDOFF; отправка и CI — в GitHub.
Полные локальные доказательства: `.superpowers/sdd/2026-09-27-companion-updates/`.
Ниже исторический исполнительный чеклист; он не заменяет итог реализации выше.

## Global Constraints

- Установка/повторная установка добавляет отсутствующие RTK/Graphify и обновляет имеющиеся.
- Update обновляет только имеющиеся; актуальный Conductor не пропускает этот шаг.
- Check не устанавливает пакет/навык и не меняет пользовательский профиль.
- Только стабильные версии из официальных источников; никакого фонового обновления.
- Обновление Superpowers не запрошено; его существующая установка/активация сохраняется.
- Не пересобирать карты и не менять hooks в проектах пользователя при обновлении Graphify.
- Незнакомое происхождение не означает разрешение перезаписать произвольный бинарник.
- Сбой инструмента не откатывает готовый Conductor и не называется успехом инструмента.
- Windows/Git Bash и Linux; документация RU/EN/AZ в интеграционной задаче lifecycle.

## Review Focus

1. Старый бинарник раньше нового в PATH — не сообщать, что обычная команда обновлена (1, 3).
2. uv успешно сохранил закреплённую старую версию — сверять с последней, не только exit (2).
3. Conductor запущен Python из обновляемой среды Graphify — не разрушать свой интерпретатор (2).
4. Новая версия не запускается на машине — оставить прежнюю рабочую и сообщить отказ (2).
5. Новая версия есть, но старый/лично изменённый skill остался — отдельно проверить доставку (3).

## Файлы и интерфейс с lifecycle

Create `runtime/updater/companions.py`, `companion_inventory.py`, `companion_update.py`;
modify `install-companions.sh`, `tools/companion-download.py`, `tools/companion-python.py`,
`tools/companion-path.py`. Перенос повторно используемого кода внутрь updater допустим
только с совместимыми thin entry points в tools; установленный CLI не зависит от checkout.
Автокопирование updater payload доставляет новые модули. Изменения CLI/payload wiring,
основных установщиков и README принадлежат исполнителю lifecycle, не параллельному агенту.

Публичный интерфейс `sync(paths: Paths, mode: str, *, skip: bool = False) -> list[dict]`
в `companions.py`; mode ровно `install`, `update`, `check`. Запись результата:
`tool` (`rtk`/`graphify`), `status` (`CURRENT`/`UPDATED`/`INSTALLED`/`AVAILABLE`/
`ABSENT`/`SKIPPED`/`FAILED`), `before`, `after`, `latest` (строка версии или None),
`detail` (сообщение без секретов). При check доступное обновление = AVAILABLE;
версия неизвестна из-за сети = FAILED, не CURRENT. До возврата UPDATED/INSTALLED
проверить точный executable, обычное разрешение команды и обязательную проводку.
`sync` вызывается под общим замком; standalone тоже берёт его, вложенного захвата нет.
Корень = `CONDUCTOR_COMPANION_HOME`, если явно задан, иначе
`paths.profile / '.local/share/conductor-companions'`; проверять абсолютный canonical path.

## Task 1: Происхождение и последние стабильные версии

**Files:** create `runtime/updater/companion_inventory.py`, `qa/companions/test_inventory.py`;
modify `tools/companion-download.py`, `qa/companions/fixture.py`.

**Interfaces:** `discover(name: str, profile: Path, root: Path) -> dict | None`;
результат `name`, `executable: Path`, `version: str`, `provider: str`,
`manager: Path | None`, `root: Path`, `receipt: Path | None`.
Provider = `managed`/`uv`/`cargo-git`/`unknown`.
`latest(name: str) -> str` возвращает стабильную версию либо возбуждает ValueError/OSError.

- [ ] Добавить `InventoryTests` с TemporaryDirectory, PATH только из фикстуры,
  поддельными ответами transport и полными manager metadata:
  `test_official_cargo_is_not_crates_io_rtk`, `test_unknown_binary_is_not_adopted`,
  `test_shadowing_is_reported`, `test_prerelease_is_excluded`, `test_offline_is_not_current`.
  Для crates.io Rust Type Kit `provider == 'unknown'`; неизвестный бинарник не меняется;
  shadowing выявляет путь реально выбранной команды; fixture release `2.0.0rc1`
  не выбирается вместо stable `1.9.0`; offline возбуждает ошибку, не возвращает local version.
  Точные утверждения: `self.assertEqual(found['provider'], 'unknown')`,
  `self.assertEqual(latest('graphify'), '1.9.0')`, `with self.assertRaises(OSError)`
  вокруг offline latest. Менять фикстуру ответа, не обращаться к текущему PyPI в unit-тесте.
- [ ] Выполнить `python -B -m unittest discover -s qa/companions -p test_inventory.py -v`;
  новые проверки должны падать на отсутствующем поведении.
- [ ] Реализовать происхождение по receipt или точным metadata uv/Cargo и canonical paths,
  а не basename/подстроке. Старый managed-install без receipt признавать только по
  точной структуре/metadata из прежнего installer, иначе FAILED с пояснением.
  RTK: официальный GitHub releases/latest, tag и checksums. Graphify: официальный
  PyPI `graphifyy`, стабильный non-yanked release; конфигурация стороннего index не
  наследуется. Неподдерживаемая последняя версия не маскируется выбором старой.
- [ ] Повторить inventory и существующие download/security tests: OK на двух ОС;
  сохранить ответы источников и версии как доказательства, без записи личных токенов.
- [ ] Зафиксировать diff/proof для итогового коммита companions, пока без push.

## Task 2: Подготовить и применить обновление без потери старой копии

**Files:** create `runtime/updater/companion_update.py`, `qa/companions/test_update.py`;
modify `tools/{companion-download,companion-python,companion-path}.py`;
extend `qa/companions/test_python.py`, `qa/companions/test_persistence.py`.

**Interfaces:** `upgrade(found: dict | None, name: str, version: str, root: Path,
profile: Path) -> Path` возвращает подтверждённый executable; metadata found из задачи 1.
`probe(executable: Path, name: str, expected: str) -> None` проверяет запуск и версию.
Ошибка возвращается исключением после условного восстановления собственных изменений.

- [ ] Добавить `UpdateTests` с настоящими временными файлами и manager-процессами
  фикстуры, регистрирующими argv: `test_failed_candidate_keeps_old_tool`,
  `test_pinned_uv_version_is_not_success`, `test_later_edit_is_not_rolled_back`,
  `test_running_graphify_python_is_not_replaced`, `test_unsupported_latest_keeps_old`,
  `test_manager_metadata_stays_consistent`. После сбоя старый запуск/версия работают,
  после поздней правки она сохранена; exit 0 со старой версией возбуждает ValueError.
  Проверять executable и manager metadata, а не только наличие файла/receipt.
- [ ] Запустить `python -B -m unittest discover -s qa/companions -p test_update.py -v`;
  ожидаемые падения указывают на отсутствие upgrade, затем удерживать эти тесты при реализации.
- [ ] Реализовать managed-обновления: скачать/установить candidate отдельно, probe до
  переключения, сохранить проверенную старую копию, атомарно переключить launcher,
  повторить probe. Среду Graphify создавать сразу по окончательному versioned path:
  перемещение venv ломает встроенные пути. Receipt и резервные копии оставить под
  `~/.local/share/conductor-companions`, не под удаляемым runtime. Частичный candidate
  не становится активным; следующая попытка распознаёт незавершённое переключение.
- [ ] Реализовать только подтверждённые внешние провайдеры: uv tool для `graphifyy`,
  Cargo git для `https://github.com/rtk-ai/rtk`. Использовать их manager, не выдавать
  замену чужого файла за managed-install и не ставить crates.io `rtk`.
  Перед записью сохранить точные затрагиваемые executable/environment/metadata,
  запретить links/неизвестные цели и сверить состояние перед восстановлением.
  uv version constraint учитывать явно: upgrade с сохранённым pin не доказывает latest;
  переустановка exact stable через tool install должна оставаться в том же tool store.
  Cargo использовать официальный git + точный опубликованный ref, не произвольный HEAD.
  После сбоя подтверждать восстановление запуском прежнего инструмента и чтением
  metadata. Параллельное изменение исходной среды/реестра другим manager — конфликт:
  сохранить копии, не пытаться восстановить целиком чужое обновлённое хранилище.
- [ ] До обновления Graphify проверить, не запущен ли текущий Python из этой среды.
  Такой поток переисполнить независимым базовым интерпретатором с теми же проверенными
  аргументами до захвата замка/записи; не оставлять ожидающий родительский Python внутри
  заменяемой среды. Если независимого интерпретатора нет — FAILED, старая версия цела.
  Не устанавливать новый Python/Node молча. Проверить реальным subprocess на Windows/Linux,
  не mock-ом `sys.executable`. Исходный updater должен остаться доступен без checkout.
- [ ] Повторить update/python/persistence/security tests: OK; снять защиту версии и
  compare-before-restore в отдельной копии: assertion-FAIL, затем PASS с защитой.
  Отдельно прогнать настоящую disposable uv-среду и официальный RTK executable в песочнице;
  скрипт с расширением `.exe` не является проверкой Windows native executable.
- [ ] Сохранить proof/diff. Если manager не даёт доказуемо безопасного восстановления,
  сообщить конкретное ограничение и остановить этот provider, не ослаблять гарантию молча.

## Task 3: Координатор, проводка и контракт результата

**Files:** create `runtime/updater/companions.py`, `qa/companions/test_sync.py`;
modify `install-companions.sh`, `qa/companions/test_acquisition.py`,
`qa/companions/test_persistence.py`. Основной CLI изменяет исполнитель lifecycle.

**Interfaces:** `sync` определён выше; использует discover/latest/upgrade/probe.
Дополнительно `wire(executable: Path, name: str, profile: Path, config: Path) -> None`
в `companions.py` для подтверждённого пути и безопасного сохранения настроек.

- [ ] Добавить `SyncTests`: `test_install_adds_and_updates`, `test_update_skips_absent`,
  `test_check_writes_nothing`, `test_one_failure_does_not_hide_other_result`,
  `test_existing_skill_is_refreshed`, `test_modified_skill_is_preserved`,
  `test_shadowed_binary_is_not_reported_updated`.
  Assert: install вызывает upgrade для отсутствующего/старого, update не добавляет
  отсутствующий; check не вызывает upgrade/wire; FAILED одного не скрывает второй;
  изменённый личный skill остаётся, readiness = FAILED с пояснением конфликта.
  Точные утверждения: `upgrade_mock.assert_not_called()` для absent update,
  `wire_mock.assert_not_called()` для check, `self.assertEqual(result[0]['status'], 'FAILED')`
  для shadowed executable; fixture возвращает результаты в порядке rtk, graphify.
- [ ] Запустить `python -B -m unittest discover -s qa/companions -p test_sync.py -v`;
  зафиксировать новые падения, затем реализовать координатор с независимым итогом каждого.
  Исключение для одного инструмента не превращать в общий exit 0 готовности.
- [ ] Обновить RTK-проводку и Graphify skill после обновления через штатные команды,
  сначала в изолированной конфигурации с правильно заданными HOME/USERPROFILE/config.
  Сравнить и безопасно применить только принадлежащие инструменту записи/файлы;
  чужие hooks/настройки сохранить. Лично изменённый skill резервировать и не затирать.
  Для существующего skill сравнить пакетную версию/содержимое, не ограничиваться existence.
  Не трогать MCP/проектные hooks вне уже поддерживаемой установки без отдельного запроса.
- [ ] Shell-вход перевести на тот же sync для RTK/Graphify; существующую логику
  Superpowers сохранить. Результат FAILED даёт частичный код 3, который верхний installer
  обрабатывает отдельно, не теряя подтверждённый Conductor; `--skip-companions` остаётся.
  Проверить `python -B -m unittest discover -s qa/companions -v` на Windows/Linux: OK.
- [ ] Передать lifecycle точные изменённые файлы, сигнатуру sync, команды, полные output/exit
  и оговорки. Общая приёмка/README/commit/push/финальный Graphify принадлежат его задаче 4.

## Самопроверка и первичные источники

Раздел дополнительных инструментов спецификации покрыт задачами 1–3; глобальный
no-op update, удаление и коды выхода проверяются дополнительно в lifecycle task 4.
Каждый Review Focus имеет отрицательную проверку; никто не изменяет одновременно CLI
и companion-файлы. Команды выше — будущие проверки, а не заявление об их прохождении.

Подтверждённые первичные источники для реализации: [uv tools и ограничения upgrade](https://docs.astral.sh/uv/guides/tools/),
[uv CLI](https://docs.astral.sh/uv/reference/cli/), [официальный RTK](https://github.com/rtk-ai/rtk),
[Graphify: upgrade и повторный install навыка](https://github.com/Graphify-Labs/graphify).
Живые версии и совместимость повторно определить при выполнении, не закреплять по памяти.
