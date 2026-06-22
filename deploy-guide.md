# Deploy Guide — production-стенд Automind Studio

Инструкция для агента (Claude Code), который готовит пакет поставки продукта на боевой сервер `app-01`. Это **контракт**: следуй ему, чтобы продукт встал в существующую инфраструктуру без ручной доработки. Архитектуру и грабли см. в `CLAUDE.md`, `ams-cloud-init.md`, `add-custom-domain-app.md`.

## TL;DR — что ты собираешь

Для каждого продукта нужны три артефакта в репозитории:

1. `Dockerfile` — собирает образ, приложение слушает один HTTP-порт.
2. `.github/workflows/deploy.yml` — build → push в GHCR → deploy по SSH → уведомление в Discord.
3. `deploy/docker-compose.yml` + `deploy/.env.example` — **production**-манифест (не dev!), который ляжет в `/opt/apps/<product>/` на сервере.

Имя продукта `<product>` = имя репозитория в организации `semsys-ams`. Оно используется везде: путь на сервере, имя БД, теги роутеров.

---

## Железные правила production (нарушение = инцидент)

1. **Никаких `ports:` в прод-компоузе.** Docker публикует порты в обход ufw — это дыра в интернет. Весь внешний трафик идёт только через Traefik по docker-сети `edge`. Исключение — Traefik (он системный, уже развёрнут).
2. **`loadbalancer.server.port` = порт, который слушает приложение ВНУТРИ контейнера.** Самая частая ошибка → 502. Next.js по умолчанию 3000, FastAPI/uvicorn 8000 — сверься с Dockerfile/CMD.
3. **Никаких stateful-сервисов в прод-компоузе продукта.** PostgreSQL и Redis уже есть на `db-01` (`10.0.0.20`). НЕ поднимай свои `postgres`/`redis` контейнеры — продукт ходит в общие по приватной сети. Локальные БД оставь в отдельном `docker-compose.dev.yml` (или через `profiles: [dev]`).
4. **`build:` только в dev.** На сервере тянем готовый образ из GHCR (`image:`), собирает его GitHub Actions. В прод-компоузе `build:` быть не должно.
5. **Секреты не коммитим.** В репозитории только `.env.example` с плейсхолдерами. Реальный `.env` создаётся на сервере вручную и в git не попадает.
6. **Сеть `edge` — `external: true`.** Её создаёт инфраструктура, не продукт. Продукт к ней только подключается.
7. **`restart: unless-stopped`** на всех сервисах продукта.

---

## Файл 1. Dockerfile

Требования к образу:

- Приложение слушает **один** TCP-порт на `0.0.0.0` (не на `127.0.0.1` — иначе Traefik из соседнего контейнера не достучится). Запиши этот порт — он пойдёт в лейбл.
- Multi-stage сборка, финальный образ минимальный (alpine/slim/distroless).
- Не root-пользователь по возможности.
- Если фреймворк умеет — добавь `HEALTHCHECK`, или health-эндпоинт (`/health`, `/api/health`), пригодится.

Пример (Next.js, порт 3000):

```dockerfile
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./
EXPOSE 3000
CMD ["npm", "start"]
```

---

## Файл 2. deploy/docker-compose.yml (production)

Это то, что окажется в `/opt/apps/<product>/docker-compose.yml`. Шаблон для **поддомена** `<product>.automind-studio.ru` (wildcard-сертификат уже покрывает, ничего выпускать не надо):

```yaml
services:
  app:
    image: ghcr.io/semsys-ams/<product>:latest
    restart: unless-stopped
    env_file: .env
    networks:
      - edge          # для Traefik
      - internal      # для общения с sidecar'ами этого продукта (cron и т.п.)
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.<product>.rule=Host(`<product>.automind-studio.ru`)"
      - "traefik.http.routers.<product>.entrypoints=web,websecure"
      # ВНИМАНИЕ: порт приложения внутри контейнера (см. Dockerfile)
      - "traefik.http.services.<product>.loadbalancer.server.port=3000"

networks:
  edge:
    external: true
  internal:
```

Правила именования лейблов: имя роутера/сервиса = `<product>` без точек и спецсимволов (Traefik не любит их в именах). Если в имени репозитория есть дефис — это ок, дефисы допустимы.

**Если у продукта свой домен 2-го уровня** (`cool-product.ru`) — НЕ этот шаблон, а `add-custom-domain-app.md`: там Let's Encrypt и лейбл `tls.certresolver=le`.

**Sidecar'ы** (cron, воркеры) — в этом же compose, в сети `internal` (без `edge`, без лейблов — наружу им не надо). Достукиваются до основного приложения по имени сервиса: `http://app:3000`. Пример cron:

```yaml
  cron:
    image: alpine:3.20
    restart: unless-stopped
    depends_on: [app]
    entrypoint: /bin/sh
    command:
      - -c
      - |
        apk add --no-cache curl
        while true; do
          sleep 300
          curl -sf -H "Authorization: Bearer $${CRON_SECRET}" http://app:3000/api/cron/task || true
        done
    env_file: .env
    networks: [internal]
```

> В compose `$` в shell-командах удваивается (`$${CRON_SECRET}`), иначе его съест подстановка переменных Docker Compose.

---

## Файл 3. deploy/.env.example

Контракт переменных окружения. В репозитории — с плейсхолдерами, на сервере заполняется реальными значениями.

```dotenv
# --- PostgreSQL (db-01, только приватная сеть) ---
DATABASE_URL=postgresql://<product>:<DB_PASSWORD>@10.0.0.20:5432/<product>

# --- Redis (db-01) — НОМЕР БД СВОЙ У КАЖДОГО ПРОДУКТА, см. реестр ниже ---
REDIS_URL=redis://:<REDIS_PASSWORD>@10.0.0.20:6379/<N>

# --- S3 (медиа/файлы) ---
S3_ENDPOINT=https://s3.twcstorage.ru
S3_BUCKET=ams-media
S3_ACCESS_KEY=<S3_ACCESS_KEY>
S3_SECRET_KEY=<S3_SECRET_KEY>

# --- payment-hub (если продукт принимает платежи) ---
PAYMENT_HUB_URL=https://pay.automind-studio.ru

# --- секреты приложения ---
CRON_SECRET=<random>
```

Имена переменных подстрой под то, что реально читает приложение (проверь в коде/конфиге). Адреса `10.0.0.20` и эндпоинты — фиксированы инфраструктурой.

### Реестр номеров Redis-БД (важно — чтобы продукты не пересеклись)

Один Redis на всех, изоляция — по номеру базы (`/0`..`/15`). Перед выбором номера загляни в актуальный реестр и возьми следующий свободный:

| N | Продукт |
|---|---------|
| 0 | ams-site |
| 1 | payment-hub |
| 2 | (следующий продукт) |

Если занятых номеров много или продуктам нужна жёсткая изоляция (отдельный `FLUSHALL`, разные политики вытеснения) — не множь номера, а подними отдельный инстанс Redis на db-01 (новый контейнер, порт 6380+, свой пароль). Это инфраструктурное изменение — отметь в задаче для владельца.

---

## Файл 4. .github/workflows/deploy.yml

Универсальный workflow — копируется между продуктами без правок (имя продукта берётся из имени репозитория). Полная актуальная версия с уведомлением в Discord — в `ams-cloud-init.md`, раздел 8.2. Кратко, что он делает:

- `push` в `main` → build образа → push в `ghcr.io/semsys-ams/<product>` с тегами `latest` и `:<sha>`;
- deploy по SSH на `app-01`: `cd /opt/apps/<product> && docker compose pull && docker compose up -d && docker image prune -f`;
- джоб `notify` (`if: always()`) шлёт в Discord: продукт, версию (`<ref> @ <sha7>`), результат.

Секреты — на уровне организации `semsys-ams` (общие для всех продуктов): `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DISCORD_WEBHOOK`.

---

## Провижининг БД на db-01 (один раз перед первым деплоем)

Продукту нужны своя база и пользователь. Создаются вручную (агент готовит команды, выполняет владелец — у агента нет доступа к приватной сети):

```bash
ssh -J deploy@<IP app-01> deploy@10.0.0.20
docker exec -it postgres psql -U postgres -c "CREATE USER <product> WITH PASSWORD '<сильный_пароль>';"
docker exec -it postgres psql -U postgres -c "CREATE DATABASE <product> OWNER <product>;"
```

Пароль — этот же впиши в `DATABASE_URL` в серверном `.env`. Принцип: у каждого продукта свой пользователь и своя БД, чужие он не видит.

---

## Первый деплой — порядок и проверка

Это делается на сервере (агент даёт команды владельцу):

```bash
# 1. Папка и манифесты
ssh deploy@<IP app-01>
mkdir -p /opt/apps/<product>
# скопировать deploy/docker-compose.yml -> /opt/apps/<product>/docker-compose.yml
# создать /opt/apps/<product>/.env из .env.example с реальными значениями

# 2. Залогиниться в GHCR (один раз на сервер, если образ приватный)
echo <GH_PAT_read:packages> | docker login ghcr.io -u <user> --password-stdin

# 3. Запуск
cd /opt/apps/<product>
docker compose pull
docker compose up -d

# 4. Проверка
docker ps                                                   # контейнер Up, в PORTS нет проброса наружу
docker logs traefik 2>&1 | grep -i error | tail -5          # пусто
curl -ik https://localhost/ -H "Host: <product>.automind-studio.ru" | head -3   # HTTP 200/2xx
```

Чек-лист готовности:

- [ ] DNS: `<product>.automind-studio.ru` резолвится (wildcard `*.automind-studio.ru` уже покрывает — отдельная запись не нужна)
- [ ] `curl` с нужным `Host` отдаёт 2xx (не 404 → роутер; не 502 → порт)
- [ ] В Traefik dashboard (`traefik.automind-studio.ru`) виден роутер продукта без ошибок
- [ ] Снаружи открыт только 443 (порт приложения наружу не торчит)
- [ ] БД и Redis доступны приложению (`docker logs <product>-app-1` без ошибок подключения)
- [ ] Push в `main` → workflow зелёный → Discord-уведомление пришло

---

## Антипаттерны (если видишь это в чужом/dev-компоузе — переделай для прода)

| Антипаттерн | Почему плохо | Как надо |
|---|---|---|
| `ports: ["3000:3000"]` | Дыра в обход ufw | Убрать, трафик через Traefik/`edge` |
| Свой `postgres`/`redis` сервис | Дубль данных, второй источник правды | Подключиться к db-01 через `.env` |
| `build:` в прод-компоузе | Сборка на бою, нет версионирования | `image:` из GHCR |
| `traefik...server.port=80` при приложении на 3000 | 502 Bad Gateway | Порт = реальный порт приложения |
| Реальный `.env` в git | Утечка секретов | Только `.env.example` |
| Один Redis-номер на два продукта | Пересечение ключей | Свой `/<N>` по реестру |
| `entrypoints=web` (без websecure) | Нет HTTPS-роутинга | `web,websecure` |
| Приложение слушает `127.0.0.1` | Traefik не достучится → 502 | Слушать `0.0.0.0` |

---

## Что агент НЕ делает сам

- Не выполняет команды на `db-01` и не лезет в приватную сеть — готовит команды, выполняет владелец.
- Не создаёт/не меняет ресурсы в панели Timeweb (LB, серверы, S3) — это инфраструктурный уровень.
- Не трогает `/opt/infra` (Traefik) — общий для всех продуктов, изменение ломает всех.
- Не коммитит секреты и не вписывает реальные пароли в файлы репозитория.
