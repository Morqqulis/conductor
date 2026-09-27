# Global CLI Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Одна глобальная установка Conductor с командами install/update/uninstall,
сохранением личных данных и проверяемым восстановлением после ошибки.

**Architecture:** Расширить существующие `Paths`, `UpdatePlan` и `Transaction`;
shell-скрипты становятся совместимыми точками входа в тот же механизм.
Дополнительные инструменты обновляются после подтверждения Conductor по отдельному плану.

**Tech Stack:** Python 3.10+ standard library, Bash/Git Bash, существующий bootstrap,
unittest; Windows и Linux. Node.js — резерв для вспомогательных скриптов при сбое Python,
не новая обязательная зависимость установленного Conductor.

**Spec:** [Утверждённые границы и схема](../specs/2026-09-27-installation-lifecycle-design.md).
Статус 2026-09-27: задачи 1–4 реализованы и локально проверены; код — `3ce180a`.
Живая глобальная установка на русском проверена, память сохранена. Updater: 75 тестов на каждой
ОС (5 платформенных пропусков), bootstrap: 30 (Linux 3 пропуска), companions: 115.
Локальные команды/полные выводы: `.superpowers/sdd/2026-09-27-global-cli-lifecycle/`.
Переход uv/Cargo на отдельные копии реализован (см. отдельный план).
Карта проверяется по хешам итоговых исходников; публикация и CI — по коммиту в GitHub.
Текущий контекст и ограничения — в HANDOFF.
Ниже исторический исполнительный чеклист; итог реализации приведён выше.

## Global Constraints

- Одна глобальная установка в профиль пользователя обслуживает все его проекты.
- Поддерживаются Windows/Git Bash и Linux; документация RU/EN/AZ.
- `update --check` не меняет установленное содержимое и не выполняет восстановление.
- Уроки, результаты проверок и личные настройки не являются установочным payload.
- Не перезаписывать изменённые управляемые файлы, неизвестный CLI или чужие hooks.
- RTK, Graphify, Superpowers и личные правила проектов при uninstall остаются.
- Без GUI, сервиса, базы данных, пересборки проекта пользователя и расследования Python.
- Снимки точных затрагиваемых файлов до первой записи, сравнение перед откатом;
  существующие незакоммиченные исправления путей/проектной очистки сохранять.
- Коммиты связными проверенными частями в конце пакета, не после каждой правки;
  Graphify обновить один раз после итоговых документов.

## Review Focus

1. Прерывание после проверки файлов, но до закрытия журнала — однозначное восстановление (1).
2. Изменение только POSIX mode после сбоя — конфликт, а не разрешение перезаписать файл (1).
3. Запуск из чужого проекта или без checkout — только глобальные цели (2, 4).
4. Windows `conductor.cmd` удаляет сам себя — фактический код выхода не теряется (3).
5. Повреждённая установка без state и смешанный каталог — не повод удалять всё (3).

## Файлы и границы

`runtime/updater/transaction.py` сохраняет существующий формат снимков; новый
`recovery.py` отвечает за незавершённую операцию. `installation.py` готовит установку,
новый `removal.py` — удаление, `cli.py` связывает команды. `payload.py` остаётся
единственным рендерером. `tools/install-preflight.py`, `install-receipt.py`, `install-cli.sh`
сохраняются как совместимые входы без второго независимого алгоритма записи.
Парсер принадлежности hooks из `tools/settings-json.py` используется повторно.

## Task 1: Общий журнал и восстановление

**Files:** modify `runtime/updater/{transaction,lock,cli}.py`;
create `runtime/updater/recovery.py`, `qa/updater/test_recovery.py`;
extend `qa/updater/test_transaction.py`.

**Interfaces:** сохранить `Transaction(paths, changes, expected=None).apply(verify) -> Path`
и `rollback(paths, backup)`. Добавить `pending(paths: Paths) -> dict | None` и
`recover(paths: Paths) -> Path | None` в `recovery.py`; обе функции проверяют журнал,
`recover` вызывается только внутри `exclusive(paths)`. `pending` ничего не пишет.

- [ ] Добавить `RecoveryTests`: временный профиль через `TemporaryDirectory`, настоящий
  `Paths`, дочерний Python с остановкой через `os._exit(23)` после выбранной записи;
  инъекция только тестовая, без production-флага обхода проверки.
  `test_interrupted_apply_recovers`, `test_mode_only_edit_blocks_recovery`,
  `test_kill_after_state_write`, `test_untrusted_pending_path`, `test_lock_covers_recovery`,
  `test_next_installer_recovers_before_importing_partial_runtime`:
  `assertEqual(child.returncode, 23)`; после восстановления старые байты/mode совпадают;
  при поздней правке `assertRaises(ValueError)` и её байты/mode сохранены;
  журнал с внешним путём отвергается до записи; второй процесс не меняет файлы.
  Последний тест запускает обычный installer из полной отдельной копии source после
  прерывания: восстановление не зависит от импорта наполовину удалённого runtime.
- [ ] Запустить `python -B -m unittest discover -s qa/updater -p test_recovery.py -v`;
  получить падения на отсутствующем восстановлении, не ошибку тестовой инфраструктуры.
- [ ] Расширить транзакцию: снимок, затем атомарный pending в приватном каталоге состояния,
  затем записи и проверка, state последним, pending удаляется после подтверждения.
  Журнал ссылается только на проверенный снимок своей установки. При восстановлении
  разрешены только состояния before/after каждого файла; конфликт сохраняет обе версии.
  Существующие schema-1 снимки остаются пригодны для явного rollback. Проверять права
  вместе с байтами, включая readback. Ошибка резервирования предшествует всем записям.
- [ ] Повторить новый тест и `python -B -m unittest discover -s qa/updater -v`.
  Ожидается OK; доказать assertion-FAIL при снятии своей защиты в отдельной текущей копии.
  На Windows проверить реальный второй процесс, на Linux дополнительно mode-only случай.
- [ ] Зафиксировать доказательства и собственный diff; коммит отложить до задачи 4.

## Task 2: Установка тем же механизмом

**Files:** modify `runtime/updater/{installation,payload,transaction,cli}.py`,
`install.sh`, `install-global.sh`, `tools/{bootstrap,install-preflight,install-receipt}.py`,
`tools/install-cli.sh`; extend
`qa/bootstrap/test_unified.py`. Существующий literal-path фикс не отменять.

**Interfaces:** `prepare_install(paths: Paths, source: Path, scopes: list[str],
reply: str, skip_values: bool, revision: str | None) -> UpdatePlan`;
`verify(paths: Paths, scopes: list[str] | None = None) -> None`;
`apply_install(paths: Paths, plan: UpdatePlan, scopes: list[str]) -> Path`.
`scopes` содержит `claude`/`global`; values выводится из `skip_values`.
Прежний `prepare(paths, source, revision)` для update сохраняется.

- [ ] Расширить реальную временную установку из `qa/bootstrap/test_unified.py`:
  `test_failed_smoke_restores_first_install`, `test_repeat_install_preserves_private_data`,
  `test_global_install_ignores_working_directory`, `test_other_scope_is_not_removed`,
  `test_foreign_settings_survive`, `test_backup_failure_writes_nothing`.
  Снять до запуска bytes/modes всех целей и личной памяти; при ошибке сравнить их точно.
  Проверить `self.assertEqual(result.returncode, 0)` и
  `self.assertEqual(state['revision'], commit)` для известного bootstrap-источника;
  для dirty local-source ожидается `self.assertIsNone(state['revision'])`.
  После успеха запуск установленного CLI возвращает 0,
  файлы текущего проекта не изменены. Повторить для RU/EN/AZ и пути `profile Ж/A&B .claude`.
- [ ] Запустить `python -B -m unittest discover -s qa/bootstrap -p test_unified.py -v`;
  новый rollback-тест должен показать частичную запись старого установщика.
- [ ] Реализовать подготовку всех файлов до записи, используя `payload()` и чистые
  операции `settings-json.install/strip`; malformed/duplicate-key JSON отклонять.
  Язык выбрать до записи один раз. Объединять scope с уже установленным, не удалять
  другой scope. Verify принимает новые scopes, не читает старый/отсутствующий state.
  Первый overwrite личного файла правил — предупреждение и проверенный снимок;
  повторный overwrite ручной правки — отказ. `--skip-global-md` сохраняется.
- [ ] Убрать неконтролируемые побочные действия из shell: учесть Cursor/Antigravity JSON
  как отдельные разрешённые цели; Git config менять только в установленном реальном
  global-origin внутри профиля и только для точного старого значения Conductor.
  Неизвестный origin/смешанный template сохранить с предупреждением. Legacy-файлы
  удалять только по полному известному содержимому после снимка, без `rm -rf` корня.
  Bootstrap передаёт полученный SHA в общую операцию, не пишет receipt вне её замка.
- [ ] Выполнить `python -B -m unittest discover -s qa/bootstrap -v` и updater suite
  на Windows/Linux: OK. Проверить fault injection до/между записями и при verify,
  реальные установленные `--help` и hooks, сохранность неизвестных legacy-файлов.
- [ ] Сохранить proof/diff для общего коммита; найденные удалённые вызовы проверить
  поиском по имени, объяснить оставшиеся совместимые входы и исторические ссылки.

## Task 3: Удаление без исходников и потери личных данных

**Files:** create `runtime/updater/removal.py`, `qa/updater/test_removal.py`;
modify `runtime/updater/{cli,payload,transaction}.py`, `uninstall.sh`,
`qa/uninstall-test.sh`, `qa/bootstrap/test_launchers.py`.

**Interfaces:** `prepare_removal(paths: Paths, *, keep_lessons: bool = True) -> UpdatePlan`;
`apply_removal(paths: Paths, plan: UpdatePlan) -> Path`.
CLI `uninstall [--dry-run] [--keep-lessons | --remove-lessons]` и standalone используют
один контракт. Предлагаемый безопасный default — сохранить память; удаление уроков
требует явного `--remove-lessons`. Прежний `--keep-lessons` совместим.

- [ ] Добавить реальные sandbox-тесты `test_uninstall_without_checkout`,
  `test_cmd_self_removal_preserves_exit`, `test_private_memory_kept_by_default`,
  `test_explicit_lesson_removal`, `test_missing_state_preserves_unknown_files`,
  `test_modified_owned_file_refuses`, `test_script_and_cli_are_equivalent`.
  Успех: управляемые команды/правила отсутствуют, чужие hooks и companions байт-в-байт
  прежние, память остаётся по умолчанию. Dry-run: снимок профиля неизменен.
  Отказ: ненулевой код и отсутствие финального сообщения об успешном удалении.
- [ ] Запустить `python -B -m unittest discover -s qa/updater -p test_removal.py -v`:
  ожидается отказ старого CLI распознать uninstall; затем добавить проверки самой операции.
- [ ] Реализовать удаление только подтверждённых файлов с тем же снимком/замком;
  неизвестные остатки не удалять. Без state использовать лишь точное распознавание
  поддерживаемого legacy-содержимого; неоднозначность означает сохранение и явный отказ.
  Глобальный личный `CLAUDE.md` не удалять. JSON очищать точным парсером, память/копии
  хранить вне удаляемого payload; явное удаление уроков также иметь восстанавливаемый снимок.
  Явный `--sweep-roots` standalone оставить opt-in с уже проверенным project-artifacts,
  без обещания общей транзакции всех проектов и глобальной установки.
- [ ] На Windows запустить именно установленный `.cmd`, не только `cli.py`;
  после удаления не исполнять продолжение удалённого batch-файла. Проверить восстановление
  удаления из сохранённого снимка через `python runtime/updater/cli.py --config CONFIG
  --profile PROFILE rollback --backup SNAPSHOT` из полной source-копии без установленного CLI.
  Записать эту команду с реальными путями в сообщение об удалении/копии, не обещать,
  что уже удалённая команда `conductor` сможет выполнить восстановление.
  Повторить removal suite и `bash qa/uninstall-test.sh` на двух ОС: OK.
- [ ] Сохранить proof/diff; не коммитить чужие изменения или резервные копии.

## Task 4: Связать три действия и закончить поставку

**Files:** modify `runtime/updater/cli.py`, `runtime/updater/payload.py`,
`qa/updater/test_flow.py`, `.github/workflows/ci.yml`, `README.md`, `README.en.md`,
`README.az.md`, `HANDOFF.md`, `CHANGELOG.md`; Graphify-выходы только штатным циклом.

**Interfaces:** использовать `companions.sync(paths, mode, *, skip=False)` из
[отдельного плана](2026-09-27-companion-updates.md), где mode = `install`/`update`/`check`.
Возвращаемые записи имеют tool/status/before/after/latest/detail; статус инструмента не
переименовывается в успех Conductor. Код 0 — весь запрошенный поток подтверждён,
1 — ошибка Conductor, 2 — аргументы, 3 — Conductor готов, но companions не готовы,
130 — прерывание. Явный skip/отсутствующий при update не считается отказом.

- [ ] Добавить `test_current_conductor_still_syncs_companions`, `test_check_is_read_only`,
  `test_companion_failure_preserves_verified_conductor`, `test_install_uses_saved_language`:
  при неизменном SHA sync вызывается один раз с update; check не пишет;
  отказ Graphify даёт 3 и отдельный статус, новая подтверждённая версия Conductor остаётся.
- [ ] Запустить `python -B -m unittest discover -s qa/updater -p test_flow.py -v`;
  получить ожидаемые новые падения, подключить команды install/uninstall и общую
  координацию. При install без checkout получать source тем же официальным transport.
  Один замок удерживать для операций Conductor и последовательности companions;
  не входить в него повторно из вложенной функции. Status/check только сообщают pending.
- [ ] Выполнить updater/bootstrap/companions/project_artifacts suites и uninstall/lint
  на Windows/Linux; это затронутая поверхность установки, а не все тесты каждого проекта.
  Перечислить platform skips. Сделать реальный no-clone sandbox install → update →
  uninstall с установленными launcher-ами; сетевые сценарии отдельно от fake transport.
  Отдельно проверить: свежая установка не зависит от директории скачанного архива после
  её удаления; новое `conductor install` и standalone uninstall запускаются автономно.
- [ ] Обновить три README, HANDOFF и CHANGELOG фактическим контрактом и ограничениями,
  затем карту Graphify один раз. Успех extraction не заменяет проверку опубликованного графа.
- [ ] Сверить staged diff с доказательствами и исходными снимками; оформить отдельные
  логические коммиты текущих исправлений, lifecycle и companions, затем разрешённый push.
  CI/живая переустановка имеют собственный статус; pending не называть успешным.

## Самопроверка плана

Транзакция/восстановление → 1; единая установка/язык/настройки → 2;
CLI и standalone удаление → 3; совместная поставка/три языка/Graphify → 4.
Пять Review Focus привязаны к тестам. Runtime-код уже изменён; живая пользовательская
установка пока не менялась. Фактические результаты отделены от исходного чеклиста выше.
