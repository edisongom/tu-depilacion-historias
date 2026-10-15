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

El token se renueva solo cada mes con `refresh-token.yml` (`igstories token-refresh --gh-secret IG_ACCESS_TOKEN`).
El valor se pasa a `gh secret set` por stdin y nunca se imprime.

## Hosting de las imágenes

La API exige una **URL pública** al JPEG (≤ 8 MB). Opciones:

| Opción | Config |
|---|---|
| Tu sitio / Cloudflare Pages / GitHub Pages | `provider="static"`, `base_url` = carpeta pública con el contenido de `assets/ready` |
| Repo público en GitHub | `base_url = "https://raw.githubusercontent.com/USUARIO/REPO/main/assets/ready"` |
| S3 / Cloudflare R2 | `provider="s3"` + `pip install ".[s3]"` |

`preflight = true` hace un HEAD antes de publicar para fallar con un mensaje claro si la URL no sirve.

## Referencia rápida

- `config.toml`: `[account]`, `[hosting]`, `[image]`, `[[slots]]` (`time`, `days`, `tags`, `tags_by_weekday`,
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
- Cuota: 100 publicaciones por API cada 24 h (de sobra para 1–3 al día).
