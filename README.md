# igstories — publicador automático de historias de Instagram

Publica cada día una historia elegida de tu catálogo de imágenes (posts ya hechos, tarjetas, etc.)
usando la **Instagram Graph API (Content Publishing)**. Pensado para correr gratis en GitHub Actions.

## Cómo funciona

```
config.toml ─┐
stories.toml ─┼─► schedule (qué toca hoy) ─► publisher ─► Graph API
history.json ─┘                                 │            1. POST /{ig}/media (STORIES, image_url)
assets/ready/*.jpg ─► hosting (URL pública) ────┘            2. GET  /{container}?fields=status_code
                                                             3. POST /{ig}/media_publish
```

- **Cron cada 30 min + lógica "due"**: no depende de que el cron sea exacto. Publica cada *slot* cuya hora
  local ya pasó (dentro de `grace_minutes`). Maneja UTC vs. hora de Chile y cambios de horario.
- **Idempotente**: historial por `YYYY-MM-DD:slot`. Reejecutar nunca duplica.
- **Resultados ambiguos** (timeout en `media_publish`): nunca se reintenta a ciegas; se consulta `/stories`
  para saber si salió. Si no se puede confirmar queda `unknown` y te avisa.
- **Selección**: filtra por tags (por día de la semana), respeta `cooldown_days`, elige la menos reciente.
  `overrides` para fechas puntuales (forzar o saltar).
- **Imágenes**: normaliza a 1080×1920 JPEG con fondo difuminado y zonas seguras de Instagram.

## Inicio rápido

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
igstories prepare            # assets/source -> assets/ready (1080x1920 JPEG)
igstories verify             # valida config, catálogo e imágenes
igstories plan --days 14     # simula las próximas publicaciones
export IG_ACCESS_TOKEN=...   # solo en tu terminal; jamás en el repo ni en chats
igstories verify --online    # comprueba token y cuenta
igstories publish --dry-run  # prueba sin publicar
igstories post precios-rostro-brazos   # primera publicación manual
```

Los tests (sin red ni credenciales): `PYTHONPATH=src:tests python -m unittest discover -s tests`.

## Configuración de Meta (verifícalo en la documentación vigente)

1. Cuenta de Instagram **Profesional** (Business o Creator).
2. Crear una app en developers.facebook.com con el producto *Instagram* (API con Instagram Login) o
   *Facebook Login* si la cuenta está vinculada a una página.
3. Permiso `instagram_business_content_publish` (o `instagram_content_publish` con Facebook Login).
   Para tu **propia** cuenta normalmente basta con modo desarrollo y tu usuario como tester/administrador;
   confirma en la documentación si hoy exigen App Review.
4. Generar un **token de larga duración** (60 días) y obtener el `ig_user_id`. Ponlo en `config.toml`.
5. En GitHub: *Settings → Secrets and variables → Actions*: `IG_ACCESS_TOKEN`, y opcionalmente
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GH_ADMIN_TOKEN` (PAT con *Secrets: write* para renovar el token).

### Renovación automática del token

`refresh-token.yml` renueva el token los días 1 y 15 de cada mes y guarda el nuevo valor en el secreto
`IG_ACCESS_TOKEN` (`igstories token-refresh --gh-secret IG_ACCESS_TOKEN`). El valor viaja por stdin a
`gh secret set` y nunca se imprime. GitHub no deja que un workflow cambie sus propios secretos con el
token por defecto, así que necesita un token personal acotado:

1. github.com → foto de perfil → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**.
2. *Repository access*: **Only select repositories** → `tu-depilacion-historias`.
3. *Permissions → Repository permissions → **Secrets: Read and write*** (nada más).
4. Genera, copia y guárdalo como secreto del repo con el nombre `GH_ADMIN_TOKEN`.
5. Pruébalo: Actions → **refresh-token → Run workflow**. Debe terminar en verde.

Si falla (token vencido del todo o `GH_ADMIN_TOKEN` mal configurado) el workflow termina en rojo y,
si configuraste Telegram, te avisa.

### Avisos por Telegram (opcional)

1. En Telegram habla con **@BotFather** → `/newbot` → copia el token del bot.
2. Escríbele cualquier mensaje a tu bot nuevo y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates`; copia `chat.id`.
3. Secretos del repo: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. Recibirás los errores; para recibir
   también los éxitos, añade `NOTIFY_SUCCESS: "1"` en el `env` de los workflows.

## Hosting de las imágenes

La API exige una **URL pública** al JPEG (≤ 8 MB). Opciones:

| Opción | Config |
|---|---|
| Tu sitio / Cloudflare Pages / GitHub Pages | `provider="static"`, `base_url` = carpeta pública con el contenido de `assets/ready` |
| Repo público en GitHub | `base_url = "https://raw.githubusercontent.com/USUARIO/REPO/main/assets/ready"` |
| S3 / Cloudflare R2 | `provider="s3"` + `pip install ".[s3]"` |

`preflight = true` hace un HEAD antes de publicar para fallar con un mensaje claro si la URL no sirve.

## Agregar imágenes sin tocar código

1. Sube tus imágenes (JPG o PNG) a la carpeta `assets/source/`. Lo más simple es desde github.com:
   repo → `assets/source` → **Add file → Upload files**.
2. Listo. En el siguiente ciclo (≤30 min) el robot las convierte a 1080×1920 (`igstories prepare`), las
   guarda en `assets/ready/` y las suma solas al catálogo con la etiqueta `libre`
   (`[catalog] autodiscover`). **Las que nunca se han publicado salen primero**; después rota la menos
   reciente, respetando `default_cooldown_days`.
3. Para sacar una imagen de la rotación, bórrala de `assets/source/` y de `assets/ready/`.
   Para darle texto de nota, prioridad, fechas de vigencia o etiquetas propias, agrégala en
   `content/stories.toml` (la entrada manual manda sobre la automática).

Si trabajas desde tu PC, haz siempre `git pull` antes de `git push`, porque el robot también sube cosas.

## Videos (.mp4)

Sube tus videos a `assets/source/` igual que las imágenes. En `igstories prepare`:

- Si ya cumplen lo que pide Meta (MP4, H.264, AAC o sin audio, 9:16, hasta 60 s, hasta 100 MB) se copian
  tal cual.
- Si no (formato horizontal, otro códec, más de 60 s) se convierten con `ffmpeg` a 1080×1920 y se recortan
  a 60 s. GitHub Actions instala `ffmpeg` solo; en tu PC hay que instalarlo si quieres convertir ahí.
- Desde el navegador de GitHub el límite de subida es de 25 MB por archivo.

Entran al catálogo igual que las imágenes y se publican con `video_url`. Los videos tardan más en
procesarse en Instagram (el programa espera hasta 7 min).

## Diagnóstico: `igstories doctor`

Revisa el token (largo, espacios, comillas, prefijo), pregunta a Instagram quién eres, consulta la cuota
y comprueba que la URL pública de una imagen responda. Si algo falla, muestra el código de error de Meta.
El workflow `publish-stories` lo ejecuta en cada ciclo, así que el registro de GitHub siempre trae el
diagnóstico. Nunca imprime el token.

## Horarios: fijos o aleatorios

Cada `[[slots]]` puede usar `time = "12:30"` o `window = ["08:00", "11:00"]`. Con `window` la hora cambia
cada día de forma pseudoaleatoria pero estable (se calcula con un hash de día+slot, así todas las
ejecuciones coinciden). La configuración por defecto es:

- `manana`: entre 08:00 y 11:00
- `noche`: entre 20:00 y 23:00

Entre una historia y la siguiente pasan siempre entre 9 y 15 horas. GitHub Actions no garantiza el cron
de 30 min: en la práctica puede espaciar las ejecuciones varias horas, por eso `grace_minutes = 600` deja
reintentar hasta 10 h después. Para publicar a la hora exacta hay que disparar el workflow desde un
servicio externo (cron-job.org con la API de GitHub `workflow_dispatch`). `igstories plan --days 7` te muestra
las horas y las historias previstas.

## Referencia rápida

- `config.toml`: `[account]`, `[hosting]`, `[image]`, `[[slots]]` (`time` o `window`, `days`, `tags`, `tags_by_weekday`,
  `grace_minutes`, `max_attempts`), `[[overrides]]` (`date`, `slot`, `story`, `skip`).
- `content/stories.toml`: `id`, `image`, `tags`, `priority`, `cooldown_days`, `active_from/active_to`, `enabled`.
- Estados del historial: `pending → publishing → published`; `failed` (reintenta hasta `max_attempts`),
  `unknown` (revisar a mano en Instagram y editar `state/history.json`), `skipped`.
- Comandos: `plan`, `prepare`, `verify [--online]`, `publish [--dry-run]`, `post ID`, `status`, `history`, `token-refresh`.
- Códigos de salida: 0 ok, 1 fallo de publicación/API, 2 configuración inválida.

## Cómo extenderlo

- **Otro hosting**: implementa `UrlProvider.url_for(path)` en `hosting.py` y regístralo en `make_provider`.
- **Otro aviso** (Slack, email): implementa `Notifier.notify(msg, level)` en `notify.py`.
- **Otra política de selección**: `schedule.pick_story` es una función pura; cambia `_sort_key`.
- **Más slots al día**: añade `[[slots]]` con otro `name` y `time`.
- **Tarjetas de marca**: `python tools/make_cards.py` regenera las de `assets/source/cards`.

## Seguridad

Los secretos solo por variables de entorno/GitHub Secrets; el cliente redacta el token de logs y errores.
No uses librerías no oficiales de Instagram (violan los términos y arriesgan el bloqueo de la cuenta).

## Límites conocidos (sin verificar contra Instagram real)

- La versión por defecto `api_version = "v23.0"` puede estar desactualizada: súbela si Meta la retira.
- La reconciliación usa `GET /{ig-id}/stories`; confirma que está disponible con tu tipo de token.
- No se ha probado con una cuenta real: haz la primera publicación con `igstories post ...` y vigílala.
- Las historias de Instagram no admiten stickers/enlaces/música vía API.
- Cuota: 50 publicaciones por API cada 24 h (de sobra para 1–3 al día).
- Según la documentación de Meta, las historias por API solo funcionan con cuentas **Business** (no Creator).
