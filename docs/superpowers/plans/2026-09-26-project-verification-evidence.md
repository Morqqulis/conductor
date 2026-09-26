# Project Verification Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Дать агентам отдельные по проектам сохранённые результаты реальных проверок,
которые можно сопоставить с нынешними условиями без обязательного повторного запуска.

**Architecture:** Явный Python-регистратор запускает команду и атомарно сохраняет запись
с двумя снимками входов и полными потоками вывода. Read-only проверка сравнивает условия,
но не исполняет сохранённую команду и не объявляет старый успех новым прогоном.

**Tech Stack:** Python standard library, Bash-установщики, unittest; Windows и Linux.

**Spec:** [Утверждённая спецификация](../specs/2026-09-26-project-verification-evidence-design.md).

Статус: задачи 1–5 реализованы и проверены на Windows/Linux (80 тестов).
Задача 6 — финальные операции; их актуальный результат ведётся в журналах
`qa/reports/evidence-2026-09-26.log` и `qa/reports/graphify-2026-09-25/finalization.log`.
Пункты задачи 6 ниже — критерии приёмки, не неподтверждённые флажки завершения.
Частые коммиты из общего навыка здесь не применяются: пользователь выбрал фиксацию
законченного пакета. Graphify запускается после финальных изменений документов.

## Global Constraints

- Только стандартная библиотека Python; ни сервера, ни внешней БД, ни сетевой отправки.
- Команды: `run`, `list`, `show`, `check`. `run` всегда выполняет указанную команду.
- `list`: по умолчанию 20 последних записей; `--limit` допускает 1–1000.
- Суммарный лимит вывода одного запуска — 64 MiB; усечённый вывод не является полным.
- `execution`: `succeeded`, `failed`, `interrupted`, `recording_error`.
- `check`: `MATCH`, `CHANGED`, `INDETERMINATE`, `INVALID`, `NOT_SUCCESSFUL`.
- `check` exit 0 только для `MATCH`, 1 для неприменимости/неизвестности, 2 для неверного
  вызова/повреждения. `MATCH` не означает полноту проверки или автоматический пропуск тестов.
- Windows: `%LOCALAPPDATA%/Conductor/evidence`; иначе
  `${XDG_STATE_HOME:-~/.local/state}/conductor/evidence`; переопределение —
  абсолютный `CONDUCTOR_EVIDENCE_HOME`. Ни Git, ни резервирование уроков не включают данные.
- POSIX-права каталогов/файлов 0700/0600; Windows — пользовательский каталог и его ACL.
- `.git` никогда не часть снимка входов. Других автоматических исключений по Git ignore нет.
- `environment` дополнительно включает PATH, PATHEXT, PYTHONPATH, PYTHONHOME,
  NODE_OPTIONS, LANG, LC_ALL, LC_CTYPE и TZ. Значения не хранятся; сравнение через HMAC.
- Никакого `shell=True`, `eval`, автоустановки зависимостей и автомодификации PATH.
- Сохранить русский, английский и азербайджанский; не добавлять имена моделей в правила.
- Текущие dirty/untracked-файлы принадлежат существующей работе. До записи каждого пути
  сохранить точные байты/существование, затем учитывать только собственные изменения.

## Review Focus

1. Проверка выводит большой stderr при занятом stdout: регистратор не зависает — задача 3.
2. Каталог проекта пересоздан по старому адресу: чужая история не наследуется — задача 1.
3. Два процесса впервые создают ключ окружения: существующий ключ не заменяется — задача 3.
4. Повреждённый ID/путь или ссылка в хранилище: чтение не выходит за его границы — задача 3.
5. Установка только для Codex и путь с пробелами/Unicode: инструмент доступен без
   исходников и установки Claude Code, а личные данные сохранены — задача 5.

## Файлы и общие интерфейсы

Новые production-файлы только в `runtime/evidence/`:
`__init__.py`, `contract.py`, `identity.py`, `inputs.py`, `store.py`, `pipe_io.py`,
`process.py`, `assessment.py`, `commands.py`, `cli.py`, `record_schema.py`.
Валидация завершённой записи вынесена из общего контракта в record_schema при задаче 3.
Это отдельные обязанности, не требование искусственно дробить каждую функцию.

Тесты — `qa/evidence/test_*.py`; обычный запуск
`python -B -m unittest discover -s qa/evidence -v`.
Тестовые репозитории, процессы, ключи и записи — только в `TemporaryDirectory`.
Не подменять глобальные HOME/USERPROFILE; перенаправлять конфиг установщика и evidence home
отдельно. Временные метки/счётчики тестов хранить вне заявленных входов.

Общие типы фиксируются задачей 1 в `contract.py` (dataclass/JSON-представление):

- `RunSpec`: `schema_version=1`, `name`, `argv: tuple[str]`, `cwd`, `inputs: tuple[str]`,
  `environment: tuple[str]`, `external_state`, `timeout_seconds`.
- `DirectoryIdentity`: `device: str`, `file_id: str`, `birth_ns: int | None`.
- `ProjectIdentity`: `root: Path`, `key: str`, `kind: str`, `directory_id: DirectoryIdentity`,
  `git_directory_id: DirectoryIdentity | None`, `issues: tuple[str]`.
- `Snapshot`: `digest: str`, `entries: list[dict]`, `environment_hmac: str | None`,
  `environment_key_id: str | None`, `executable: dict`, `tool_digest: str`, `issues: list[str]`.
  Entry: `path`, `kind`, `size`, `executable_bits`, `sha256`; directory entries фиксируют
  пустые/добавленные каталоги. Executable: канонический `path`, `size`, `sha256`.
- `ProcessResult`: `execution`, `exit_code: int | None`, `duration_ms`, `stdout_bytes`,
  `stderr_bytes`, `stdout_sha256`, `stderr_sha256`, `output_complete: bool`, `errors: list[str]`.
- `RunHandle`: `id: str`, `directory: Path`, `project: ProjectIdentity`.
- `Assessment`: `status: str`, `reasons: list[str]`, `limitations: list[str]`.
- `EvidenceError(code: str, message: str)`: ожидаемая ошибка с безопасным сообщением;
  сообщения не включают значения окружения или полный вывод ребёнка.

Формат `record.json`: `schema_version`, `id`, `created_at`, `finalized`, `project`,
`spec`, `before`, `after`, `process`, `limitations`. Вложенные поля соответствуют типам.
Path сериализуется строкой, tuple — массивом; JSON запрещает NaN/Infinity, повторяющиеся
и неизвестные ключи на каждом уровне. `environment_key_id` — SHA-256 локального ключа,
не значение переменной; смена ключа отличается от смены окружения.
Пути к stdout/stderr вычисляются из проверенного RunHandle, не из полей JSON.
Версию кода регистратора считать SHA-256 упорядоченных production `.py` этого пакета,
исключая bytecode; изменение документации не меняет этот отпечаток.

---

### Task 1: строгий контракт и идентичность проекта

**Files:** создать `runtime/evidence/{__init__,contract,identity}.py`,
`qa/evidence/test_contract.py`, `qa/evidence/test_identity.py`.

**Interfaces:**
- `parse_spec(data: dict) -> RunSpec`; `to_json(value) -> dict` для общих dataclass;
  `from_record(data: dict) -> dict` проверяет весь формат завершённой записи.
- `identify_project(path: Path) -> ProjectIdentity`.
- `resolve_executable(argv0: str, cwd: Path, env: dict[str,str]) -> Path`.

- [x] Добавить отрицательные тесты контракта и разделения проектов, включая
  `test_recreated_root_changes_identity`, `test_worktrees_are_distinct`,
  `test_rejects_unknown_or_duplicate_json_fields`, `test_rejects_cmd_without_interpreter`.
  JSON-дубликаты отклонять при загрузке, а не после потери ключа парсером.
  Ядро assertions:
  ```python
  self.assertNotEqual(identify_project(repo_a).key, identify_project(repo_b).key)
  self.assertNotEqual(identity_before.key, identify_project(recreated_repo).key)
  with self.assertRaises(EvidenceError):
      parse_spec(dict(valid_spec, timeout_seconds=float("nan")))
  ```
- [x] Запустить `python -B -m unittest discover -s qa/evidence -p 'test_contract.py' -v`
  и аналогично `test_identity.py`; зафиксировать красный результат отсутствующей реализации.
- [x] Реализовать типы и валидацию: непустой argv/inputs, только строки без NUL,
  cwd внутри проекта, конечный положительный timeout, две допустимые external_state,
  недопустимость bool вместо числовой версии/timeout. Семантику пустой environment сохранить.
- [x] Реализовать канонизацию и ID: SHA-256 нормализованного корня, вида проекта,
  directory identity и Git metadata identity. Для них учитывать время создания, не mtime/ctime:
  Windows — file identity/creation time, Linux — statx birth time с проверкой доступности.
  Один inode может повторно выдаваться после удаления; без времени создания отмечать
  ненадёжную идентичность, не разрешать MATCH. Не создавать маркеры в проекте.
  Git-команды read-only, аргументы массивом;
  ошибка Git не маскируется под non-Git. Недоступный/нулевой filesystem identity даёт issue.
  Псевдонимы одного каталога совпадают; отсутствие/смена каталога не совпадает.
- [x] Повторить оба файла тестов: ожидается `OK`, exit 0. Проверить happy path,
  пустое/некорректное описание, Unicode/пробелы, non-Git, worktree и недоступный каталог.
  Отдельный тест с одинаковым file_id и разным birth_ns исключает случайное прохождение
  только за счёт нового inode; неизвестный birth_ns должен оставлять issue.

### Task 2: наблюдаемые входы и окружение

**Files:** создать `runtime/evidence/inputs.py`, `qa/evidence/test_inputs.py`.

**Interfaces:** потребляет типы задачи 1;
`capture_inputs(project: ProjectIdentity, spec: RunSpec, env: dict[str,str],
key: bytes | None) -> Snapshot`. Ключ получает снаружи; хранилище не открывает.

- [x] Добавить `test_untracked_addition_changes_snapshot`, `test_git_commit_is_not_input`,
  `test_unrelated_readme_does_not_change_snapshot`, `test_absent_env_differs_from_empty`,
  `test_links_and_unreadable_inputs_are_incomplete`, `test_environment_values_not_serialized`.
  ```python
  self.assertEqual(before.digest, after_unrelated_edit.digest)
  self.assertNotEqual(before.digest, after_new_input.digest)
  self.assertNotEqual(absent.environment_hmac, empty.environment_hmac)
  self.assertNotIn(secret_value, json.dumps(to_json(snapshot)))
  ```
- [x] Запустить `python -B -m unittest discover -s qa/evidence -p 'test_inputs.py' -v`;
  ожидать FAIL до реализации.
- [x] Реализовать детерминированный обход заявленных путей, исключение `.git`, хеширование
  байтов и изменения файла во время его чтения. Перекрывающиеся входы объединяются
  в один упорядоченный набор, без повторных entries. Абсолютные пути и выход через `..`
  отклонять до запуска; недоступный файл внутри допустимой области оставляет issue.
  Symlink/reparse point не обходить; записывать причину неполноты. Не читать цели вне корня.
  Совпадение исходного и повторного stat — ограниченное наблюдение, не защита от ABA.
- [x] Реализовать HMAC-SHA256 канонического набора имён/значений, различая отсутствие;
  учитывать фиксированный список из Global Constraints, platform/arch, executable и код
  регистратора. Отсутствующий ключ и неизвестная версия не могут создать положительное доказательство.
- [x] Повторить тесты: `OK`, exit 0; проверить неизменность результатов при новом commit,
  изменчивость при байтах/конфиге/окружении/удалении/переименовании и отказ для `.git` как входа.

### Task 3: реальный процесс и атомарная запись

**Files:** создать `runtime/evidence/{store,pipe_io,process}.py`,
`qa/evidence/test_store.py`, `qa/evidence/test_process.py`.

**Interfaces:** потребляет типы/identity задачи 1, не зависит от реализации inputs:
- `evidence_home(env: dict[str,str]) -> Path`;
  `load_key(home: Path, create: bool) -> bytes | None`.
- `begin_run(home: Path, project: ProjectIdentity) -> RunHandle`;
  `finish_run(handle: RunHandle, spec: RunSpec, before: Snapshot, after: Snapshot,
  result: ProcessResult) -> dict`.
- `load_run(home: Path, project: ProjectIdentity, run_id: str) -> dict`;
  `list_runs(home: Path, project: ProjectIdentity, limit: int = 20) -> list[dict]`.
- `read_ready(stream: BinaryIO, maximum: int) -> bytes | None`: None — пока нет данных,
  пустые bytes — EOF; неблокирующий обход обоих каналов.
- `capture_process(argv: tuple[str], cwd: Path, env: dict[str,str], directory: Path,
  timeout_seconds: float, limit_bytes: int = 67108864) -> ProcessResult`.

- [x] Написать тесты на реальных дочерних Python-процессах: две большие строки в разных
  потоках, бинарные/невалидные UTF-8 байты, код 7 при тексте PASS, timeout и удерживающий
  pipe потомок. Для потока лимитировать запись, продолжая отводить данные без накопления в RAM.
  ```python
  self.assertEqual(result.exit_code, 7)
  self.assertEqual(stdout_path.read_bytes(), expected_stdout)
  self.assertFalse(over_limit.output_complete)
  self.assertLessEqual(over_limit.stdout_bytes + over_limit.stderr_bytes, 67108864)
  ```
- [x] Добавить `test_concurrent_first_key_creation`, `test_concurrent_runs_stay_separate`,
  `test_tampered_record_and_stream_rejected`, `test_store_path_escape_and_link_rejected`,
  `test_atomic_finalize_failure_is_not_success`, `test_missing_or_changed_key_is_unknown`.
  Первый ключ создают два настоящих процесса;
  на обоих концах проверяется один и тот же ключ, не только отсутствие исключения.
- [x] Выполнить отдельно `test_process.py` и `test_store.py` через unittest discover;
  записать ожидаемые красные результаты перед реализацией соответствующей области.
- [x] Реализовать store: приватные каталоги, UUID, exclusive-create ключа, промежуточная
  finalized=false запись, flush/fsync и атомарная замена готовых метаданных. Проверять
  проект, формат, размеры/хеши потоков. Read-only вызовы не создают отсутствующий ключ.
  Запрещать evidence home внутри проверяемого проекта; установка не создаёт хранилище.
  Повреждённый ключ не заменять молча. Потеря/смена key ID исключает сравнение HMAC.
  При ошибке записи сохранить доступную диагностику, не затронуть чужие записи.
- [x] Реализовать Popen с argv, shell=False, DEVNULL и binary PIPE. Отводить оба потока
  одним циклом: POSIX — nonblocking read; Windows — PeekNamedPipe перед чтением доступных
  байтов через ctypes/msvcrt. Не использовать бесконечный read или communicate, накапливающий
  весь вывод. При отсутствии данных ожидание не более 50 ms; при данных продолжать сразу.
- [x] Timeout/interrupt: прекратить ожидание, завершить принадлежащий запуску процесс,
  ограничить дренирование каналов 2 секундами после завершения/отмены. Незакрытый pipe
  потомка пометить неполным и закрыть; не ждать его бесконечно и не заявлять полную очистку
  всех процессов дерева. Не завершать процессы по имени или глобальным поиском.
- [x] Повторить обе группы: `OK`, exit 0. На Windows отсутствие прав на symlink не даёт
  права незаметно пропустить проверку junction/reparse; выполнить доступный junction-сценарий.

### Task 4: CLI и честное сравнение сохранённого результата

**Files:** создать `runtime/evidence/{assessment,commands,cli}.py`,
`qa/evidence/test_assessment.py`, `qa/evidence/test_cli.py`.

**Interfaces:** использует задачи 1–3;
`assess(record: dict, project: ProjectIdentity, current: Snapshot) -> Assessment`;
`main(argv: list[str] | None = None) -> int`.
`cli.py` — тонкий вход, работающий по абсолютному пути вне репозитория;
внутренние импорты не зависят от cwd и не подхватывают одноимённые файлы проверяемого проекта.

- [x] Создать end-to-end fixture со счётчиком запусков вне inputs. Проверить
  run/show/list/check, новый commit и постороннюю правку, затем значимое изменение,
  другой проект, повреждение потока, environment unknown и ошибку записи при child exit 0.
  ```python
  self.assertEqual(run_result.returncode, 0)
  self.assertEqual(check_json["status"], "MATCH")
  self.assertEqual(counter.read_text(), "1")
  self.assertEqual(changed_json["status"], "CHANGED")
  self.assertNotEqual(foreign_check.returncode, 0)
  self.assertNotEqual(recording_error.returncode, 0)
  ```
- [x] Запустить по отдельности `test_assessment.py`, `test_cli.py` — ожидается FAIL.
- [x] Реализовать приоритет решений: неверный формат/целостность → INVALID;
  другой проект или неполные наблюдения/unknown → INDETERMINATE; неуспех выполнения →
  NOT_SUCCESSFUL; обнаруженное изменение → CHANGED; иначе MATCH с явными limitations.
  Два одинаково неполных снимка никогда не MATCH. Без сохранённой успешной записи нет MATCH.
  Сравнивать все три снимка: before, after и current. Отличие before от after не исчезает,
  даже если нынешние файлы совпали с after; тест меняет свой вход и доказывает отказ от MATCH.
- [x] Реализовать CLI: описанный JSON-контракт, stderr отдельно, stdin закрыт ребёнку,
  child returncode в метаданных без переинтерпретации. При POSIX signal хранить отрицательный
  код, CLI возвращает 128+signal; внутренние ошибки exit 2, timeout exit 124. `show` и
  `check` не запускают сохранённый argv. ID валидируется до доступа к диску.
- [x] Повторить две группы и весь `python -B -m unittest discover -s qa/evidence -v`:
  ожидается `OK`, exit 0. В изолированной текущей копии снять только guards mismatch,
  foreign-project и incomplete по одному: нынешние отрицательные тесты должны упасть
  на assertions; возврат guard восстанавливает PASS. Не удалять тесты/импорты ради красного.

### Task 5: установка, обнаружение агентом и три языка

**Files:** изменить `install.sh`, `install-global.sh`, `runtime/playbooks/verification.md`,
`adapters/core-body.md`, `.github/workflows/ci.yml`, `README.md`, `README.en.md`, `README.az.md`;
создать `qa/evidence/test_install.py`, `qa/evidence/test_discovery.py`.
Генерируемые adapters обновляются только `tools/build-digests.sh`.
`tools/doctor.sh` менять лишь при доказанной необходимости: сейчас он перечисляет runtime целиком.
Core/subagent-contract не расширять: их бюджет почти исчерпан.

**Interfaces:** установленный `evidence/cli.py` с CLI задачи 4, существующие флаги
`--language` и `--skip-companions`, без изменения их семантики.

- [x] До изменения инструкций выполнить три короткие реальные задачи без новой подсказки:
  тот же проект без изменений, значимый изменённый вход, второй проект. Сохранить реальные
  команды/счётчик запусков/решения в маленьком журнале контрольной группы вне runtime.
  В исходных пробах регистратор не доступен исполнителю; само наличие уже написанного
  кода не превращает их в испытание новой функции.
  Не подменять выполнение выбором ответа в воображаемой ситуации; не заявлять ускорение
  при отсутствии лишнего повторного запуска в исходном поведении.
- [x] Добавить тесты установки в временный CLAUDE_CONFIG_DIR с пробелами/Unicode для
  обоих установщиков по отдельности. Запускать установленный CLI с cwd вне исходников;
  повторная установка не меняет байты личных настроек сверх штатной операции и evidence data.
  Изолировать companion-команды и реальную конфигурацию git. Проверить отсутствие Python.
  ```python
  self.assertEqual(installed_cli.returncode, 0)
  self.assertEqual(before_receipt_bytes, receipt_path.read_bytes())
  self.assertEqual(before_lesson_bytes, lesson_path.read_bytes())
  self.assertIn("evidence", missing_python.stderr + missing_python.stdout)
  ```
- [x] Прогнать `test_install.py` и зафиксировать FAIL для установки только через
  install-global. Затем доставить один и тот же evidence-пакет обоими установщиками;
  вывести его фактический путь. Данные не создавать/не переносить при установке.
  Отсутствие Python в install-global даёт явную недоступность функции, не поломку правил.
- [x] После исходных проб добавить компактную добровольную подсказку в verification и
  общий digest: путь относительно Conductor home; при его определении CLAUDE_CONFIG_DIR
  приоритетнее ~/.claude. Проверять наличие инструмента, не угадывать абсолютный путь автора.
  Указать, что MATCH не PASS и обычные запуски/inspection-only завершение остаются допустимы.
  В `test_discovery.py` проверять реально отрендеренные поверхности RU/EN/AZ, не только исходник.
- [x] Обновить три README существующим компактным разделом: назначение, явный run,
  разделение проектов, локальные чувствительные данные, ограничения зависимостей/ссылок.
  Добавить в CI `python -B -m unittest discover -s qa/evidence -v`, сохранив все старые steps.
- [x] Выполнить те же три реальные задачи с инструментом и новой подсказкой. Сохранить
  число запусков и решения; unchanged может повторно использовать результат, changed и
  foreign-project не должны получать ложное подтверждение. Измерить также стоимость снимка;
  не утверждать экономию по одному количеству строк кода или вымышленному времени.
- [x] Выполнить `bash tools/build-digests.sh`, `bash qa/lint.sh`, `test_install.py`,
  `test_discovery.py`, всю evidence-группу и затронутый `bash qa/doctor-test.sh`.
  Ожидается exit 0; бюджеты не увеличивать для прохождения. Не дублировать уже применимые
  проверки других подсистем, но сохранить полный стандартный CI.

### Task 6: приёмка пакета и итоговое обновление Graphify

**Files:** `HANDOFF.md`, `CHANGELOG.md`, `docs/continuation-2026-09-25.md`,
существующий `qa/reports/graphify-2026-09-25/finalization.log`, обновлённые graphify data.
Один компактный журнал доказательств новой функции в `qa/reports/evidence-2026-09-26.log`;
личные результаты тестов в него не копировать.

**Interfaces:** production CLI, sandbox-installed copy, сохранённая принятая сборка Graphify.

- Интегрировать только собственные изменения. Сопоставить доказательства с фактическим
  diff; выполнить новые проверки изменившихся взаимодействий. Независимый проверяющий
  нужен для делегированного кода, который основной исполнитель не наблюдал, а не для
  повторения уже лично доказанной работы. Учитывать все 7 групп приёмки спецификации.
- Обновить текущую сводку, версии статуса спецификации/плана и журнал доказательств.
  Отдельно назвать ограничения, реально измеренный эффект и что ещё не реализовано.
  В штатную установку пользователя переносить только принятый пакет с резервной копией,
  выбранным русским языком и сверкой личной памяти; не переустанавливать спутников без нужды.
- Завершить все изменения документов перед Graphify. Сохранённые 833 узла использовать
  как исходную проверенную сборку, а не корневой старый граф. Проверить отсутствие активного
  писателя, сохранить байтовую копию. Изолировать конкретный неудачный cache entry HANDOFF,
  не удалять весь кэш; затем штатным extract обработать все накопившиеся изменения.
  Не использовать allow-partial/force для обхода потери смысла и не рисовать узлы вручную.
- Проверить полный набор нынешних документов, конечные точки связей, уникальность ID,
  источники, manifest и актуальность кэша. Только затем перенести данные в graphify-out;
  отдельный отчёт/HTML не генерировать. Старые визуальные артефакты не выдавать за новые.
- Сопоставить доказательства со staging и оформить связные коммиты без чужих файлов.
  Существующие uncommitted-правки companions сохраняются и учитываются отдельно.
  Использовать разрешение пользователя на push main; не называть CI зелёным до результата.
  Отчитаться о функции и карте вместе, не объявлять этим весь исследовательский backlog закрытым.

## Порядок исполнения и самопроверка плана

Задача 1 → задачи 2 и 3 могут идти независимо → задача 4 → задача 5 → задача 6.
Для параллельной работы: один исполнитель получает только inputs и его тест;
основной агент ведёт store/process. Общий contract после задачи 1 не меняется параллельно.
Если интерфейс пришлось изменить — сначала согласовать его, затем продолжить потребителей.
Самопроверка плана выполняется основным агентом, не дополнительным субагентом.

Покрытие спецификации: §§1–3 → 4/5; §4 → 1/4; §5 → 1/2/4; §6 → 3;
§7 → 3/4; §8 → 5/6; §9 → 6. Все пункты Review Focus имеют владельца и отрицательный тест.
Самопроверка выполнена: уточнены переиспользование файлового ID, смена ключа HMAC,
сравнение трёх снимков и границы контрольной группы. Это требования к будущей проверке,
не утверждение, что реализация уже прошла её.
Фактические прогоны и ограничения контрольной группы перечислены в журнале приёмки;
сокращение числа запусков в агентной пробе не установлено (3 против 3).

Опорные API: [Python subprocess](https://docs.python.org/3/library/subprocess.html)
для argv/returncode/потоков; [Microsoft PeekNamedPipe](https://learn.microsoft.com/en-us/windows/win32/api/namedpipeapi/nf-namedpipeapi-peeknamedpipe)
для чтения доступных байтов Windows pipe. Это обоснование выбора, не замена проверок на ОС.
Идентичность: [Linux statx](https://man7.org/linux/man-pages/man2/statx.2.html) сообщает
доступность birth time отдельно; [Windows file information](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle)
описывает идентификатор файла и ограничения файловых систем.

Пользователь утвердил план и исполнение: основная работа здесь,
один независимый исполнитель для задачи 2 после задачи 1;
проверить его интеграцию, не запускать по свежему агенту на каждое небольшое действие.
