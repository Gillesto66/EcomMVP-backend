# AGC Space — Backend MVP

Plateforme e-commerce avec système d'affiliation, builder de pages de vente et tunnel de conversion.

## Statut Frontend
- Builder V2 : phase F10.4 en cours, templates prédéfinis et undo/redo ajoutés.

## Audit rapide
- ✅ Base solide : builder visuel, affiliation HMAC, checkout ACID, thème CSS dynamique, payload `/render/`, cache Redis, PWA et tests backend/frontend.
- ⚠️ Gaps Shopify : pas de multi-domaines / multi-boutiques, pas de variantes produits avancées, pas de promotions/coupons, pas de taxes/shipping complexes, pas d’abonnements, pas d’analytics store ni d’écosystème d’apps.
- 🛠️ Correction appliquée : fix HTML du header builder dans `frontend/src/modules/builder/components/EnhancedBlockEditor.tsx` (boutons Undo/Redo dupliqués supprimés).
- 🧭 Prochaine étape : enrichissement du builder avec propriétés de bloc avancées, feed back UX, et dashboard analytics.

---

## Vue d'ensemble

AGC Space est un backend Django REST Framework qui permet à des **e-commerçants** de vendre des produits via des **pages de vente personnalisées**, en s'appuyant sur un réseau d'**affiliés** qui génèrent du trafic en échange de commissions.

### Les 3 acteurs

| Rôle | Ce qu'il fait |
|------|--------------|
| **E-commerçant** | Crée des produits, construit des pages de vente avec le Smart Builder, définit son thème visuel |
| **Client** | Visite une page de vente, achète un produit (via lien affilié ou directement) |
| **Affilié** | Génère des liens signés vers les produits, touche une commission sur chaque vente tracée |

---

## Architecture technique

```
agc_core/          → Configuration Django (settings, urls, wsgi)
users/             → Authentification JWT + système de rôles multi-rôles
products/          → Produits, Smart Builder (templates JSON), thèmes CSS, cache Redis
affiliations/      → Liens d'affiliation signés HMAC, commissions
orders/            → Commandes avec transactions atomiques ACID
deploy/            → Nginx, Gunicorn, systemd
logs/              → Logs rotatifs (10 MB × 5 fichiers)
```

### Stack

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Framework | Django 5.2 + DRF 3.16 | API REST |
| Auth | SimpleJWT | Tokens JWT (access 60min, refresh 7j) |
| Base de données | PostgreSQL 14+ | Données + index JSONB GIN |
| Cache | Redis 7 + django-redis | Pages de vente (TTL 5min), thèmes (TTL 1h) |
| Serveur | Gunicorn + Nginx | Production |
| Tests | pytest + pytest-django | 60+ tests unitaires et d'intégration |

---

## Fonctionnalités par phase

### Phase 1 — Fondations

**Authentification multi-rôles**
- Un utilisateur peut avoir plusieurs rôles simultanément (ex: Client ET Affilié)
- JWT avec rotation des refresh tokens
- Endpoints : register, login, refresh, profil, changement de mot de passe

**Modèles de données**
- `User` + `Role` (ManyToMany)
- `Product` (SKU indexé, stock, digital/physique)
- `PageTemplate` (JSONField, réutilisable entre produits)
- `AffiliationLink` (tracking_code indexé)
- `Order` + `OrderItem` (prix figé à l'achat)

---

### Phase 2 — Smart Builder

Le cœur de la plateforme. Permet de construire des pages de vente sans coder.

**Moteur de thème (Design System)**

Chaque e-commerçant a un thème avec des variables CSS :
```json
{
  "primary_color": "#FF6B35",
  "font_family": "Inter, sans-serif",
  "border_radius": "8px"
}
```
Ces variables sont injectées dans le payload de rendu. Le front React les applique via `var(--primary-color)`.

**Structure JSON des blocs**

Un template est une liste de blocs typés. Chaque bloc peut avoir des règles de visibilité :
```json
{
  "blocks": [
    {
      "type": "hero",
      "text": "Maîtrisez Django en 30 jours",
      "visibility": {}
    },
    {
      "type": "stock_status",
      "visibility": { "stock_min": 1 }
    },
    {
      "type": "buy_button",
      "label": "Acheter maintenant",
      "affiliate_aware": true,
      "visibility": { "stock_min": 1 },
      "tracking": { "event": "click_buy" }
    }
  ]
}
```

**Types de blocs disponibles**

| Type | Description | Données injectées |
|------|-------------|-------------------|
| `hero` | Bannière principale | — |
| `features` | Liste de fonctionnalités | — |
| `testimonials` | Avis clients | — |
| `social_proof` | Preuve sociale | `total_sold`, `buyer_count` (30 derniers jours) |
| `countdown` | Compte à rebours | `seconds_remaining`, `deadline_iso`, `is_expired` |
| `stock_status` | État du stock | `stock`, `label`, `level` (ok/low/out) |
| `buy_button` | Bouton d'achat | `affiliate_aware`, état du stock |
| `text` | Bloc texte libre | — |
| `image` | Image | — |
| `video` | Vidéo | — |

**Règles de visibilité conditionnelle**

```json
"visibility": { "stock_min": 5 }   // Affiche si stock >= 5
"visibility": { "stock_max": 0 }   // Affiche si stock == 0 (rupture)
"visibility": {}                    // Toujours visible
```

**Critical CSS Injection**

À chaque sauvegarde d'un template, un blob CSS est généré automatiquement :
- Seuls les types de blocs présents génèrent du CSS (lazy)
- Les variables du thème sont injectées dans `:root`
- Le CSS est retourné dans le payload `/render/` pour être injecté dans `<head>`

Résultat : zéro calcul CSS au moment du rendu.

**Endpoint de rendu**

`GET /api/v1/render/<product_id>/` — public, sans authentification.

Payload complet retourné :
```json
{
  "product": { "id": 1, "name": "Formation Django", "price": "97.00", ... },
  "theme": { "variables": { "primary_color": "#FF6B35" }, "css_preview": ":root { ... }" },
  "template": { "id": 1, "name": "Template Formation" },
  "blocks": [
    { "type": "social_proof", "data": { "total_sold": 42, "buyer_count": 38 } },
    { "type": "countdown", "data": { "seconds_remaining": 86400, "is_expired": false } },
    { "type": "buy_button", "affiliate_aware": true, "data": { "level": "ok" } }
  ],
  "critical_css": ":root { --primary-color: #FF6B35; } .block-buy-button { ... }",
  "meta": {
    "tracking_events": [{ "event": "click_buy" }],
    "affiliate_aware_blocks": ["buy_button"]
  }
}
```

Le front React consomme ce payload unique pour construire toute la page.

---

### Phase 3 — Tunnel de vente & Affiliation

**Sécurité HMAC des liens**

Les liens d'affiliation sont signés avec HMAC-SHA256. La signature couvre :
```
tracking_code:product_id:expires_at
```

Cela rend impossible :
- La falsification du taux de commission
- La substitution du produit dans l'URL
- La réutilisation d'un lien expiré

Comparaison en temps constant (`hmac.compare_digest`) — protection contre les timing attacks.

**Flow complet**

```
1. Affilié  → POST /affiliations/links/<id>/signed-url/
             ← { url: "...?ref=CODE&sig=HMAC&exp=TS", expires_at: ... }

2. Visiteur → Clic sur le lien
           → GET /affiliations/validate/?ref=CODE&sig=HMAC&exp=TS&product_id=ID
             ← { valid: true, cookie: { cookie_name: "agc_ref", tracking_code: "CODE" } }

3. Front    → Pose le cookie agc_ref=CODE (30 jours)

4. Client   → POST /orders/create/ { items: [...], referral_code: "CODE" }

5. Backend  → Transaction atomique :
               ✓ Vérification stock
               ✓ Création Order + OrderItems (prix figés)
               ✓ Décrément stock (F() expression — pas de race condition)
               ✓ Création Commission (taux figé)
             ← { order: {...}, commission: { amount: "4.50", status: "pending" } }
```

**Garanties ACID**

Tout se passe dans `@transaction.atomic` :
- Si le stock est insuffisant → rollback complet, aucune commande créée
- Si la création de commission échoue → rollback complet, aucune commande créée
- Un referral_code invalide → la vente continue sans commission (pas de blocage)

**Modèle Commission**

```
order_total    → figé au moment de la vente
commission_rate → figé au moment de la vente (indépendant des modifications futures)
amount         → order_total × commission_rate (arrondi à 2 décimales)
status         → pending → validated → paid / cancelled
```

L'admin Django permet de valider et marquer les commissions comme versées en masse.

---

### Phase 4 — Performance & Déploiement

**Cache Redis**

| Donnée | Clé Redis | TTL | Invalidation |
|--------|-----------|-----|--------------|
| Page de vente | `agcspace:render:product:<id>` | 5 min | Modification produit/template/thème |
| Thème CSS | `agcspace:theme:<user_id>` | 1h | Modification du thème |

Si Redis est indisponible, l'application continue sans cache (`IGNORE_EXCEPTIONS=True`).

**Index PostgreSQL**

| Index | Type | Sur | Utilité |
|-------|------|-----|---------|
| `products_pagetemplate_config_gin` | GIN JSONB | `config` | Recherche dans les blocs |
| `products_theme_variables_gin` | GIN JSONB | `variables` | Filtrage par variable CSS |
| `orders_order_referral_partial` | Partiel | `referral_code WHERE NOT NULL` | Requêtes affiliation |
| `affiliations_link_tracking_code_idx` | Partiel | `tracking_code WHERE is_active` | Validation liens actifs |

**Infrastructure production**

```
Internet → Nginx (SSL/TLS, headers sécurité, cache 1min /render/)
         → Gunicorn (workers = CPU×2+1, timeout 30s)
         → Django
         → PostgreSQL (connexions persistantes CONN_MAX_AGE=60)
         → Redis (cache pages de vente)
```

**Health check**

`GET /health/` — vérifie PostgreSQL et Redis, retourne `200 ok` ou `503 degraded`.

---

## Référence API complète

### Authentification

| Méthode | Endpoint | Description | Auth |
|---------|----------|-------------|------|
| POST | `/api/v1/auth/register/` | Inscription (rôle optionnel : client/ecommercant/affilie) | Non |
| POST | `/api/v1/auth/login/` | Login → `{ access, refresh }` | Non |
| POST | `/api/v1/auth/token/refresh/` | Renouveler le token | Non |
| GET/PUT | `/api/v1/auth/me/` | Profil de l'utilisateur connecté | Oui |
| POST | `/api/v1/auth/me/change-password/` | Changer le mot de passe | Oui |

### Produits & Builder

| Méthode | Endpoint | Description | Auth |
|---------|----------|-------------|------|
| GET/POST | `/api/v1/products/` | Liste / créer produits | Oui |
| GET/PUT/DELETE | `/api/v1/products/<id>/` | Détail produit | Oui |
| GET | `/api/v1/products/<id>/templates/` | Templates associés | Oui |
| GET/POST | `/api/v1/themes/` | CRUD thèmes | Oui |
| GET | `/api/v1/themes/mine/` | Mon thème (get or create) | Oui |
| GET/POST | `/api/v1/templates/` | Liste / créer templates | Oui |
| PUT/PATCH | `/api/v1/templates/<id>/` | Modifier un template | Oui |
| POST | `/api/v1/templates/<id>/assign/` | Assigner template à produit | Oui |
| GET | `/api/v1/templates/<id>/css/` | Critical CSS pré-généré | Oui |
| **GET** | **`/api/v1/render/<product_id>/`** | **Payload complet de rendu (public, mis en cache)** | **Non** |

### Affiliation

| Méthode | Endpoint | Description | Auth |
|---------|----------|-------------|------|
| GET/POST | `/api/v1/affiliations/links/` | Mes liens d'affiliation | Affilié |
| POST | `/api/v1/affiliations/links/<id>/signed-url/` | Générer URL signée HMAC | Affilié |
| GET | `/api/v1/affiliations/links/stats/` | Statistiques globales | Affilié |
| GET | `/api/v1/affiliations/commissions/` | Mes commissions | Affilié |
| GET | `/api/v1/affiliations/validate/` | Valider un lien (public) | Non |

### Commandes

| Méthode | Endpoint | Description | Auth |
|---------|----------|-------------|------|
| POST | `/api/v1/orders/create/` | Créer une commande (ACID) | Oui |

---

## Quickstart

### Backend (Django)

Temps estimé : **10 minutes**

#### Prérequis

| Outil | Version min | Obtenir |
|-------|-------------|---------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| PostgreSQL | 14+ | [postgresql.org/download](https://www.postgresql.org/download/) |
| Redis | 7+ | Voir ci-dessous |

#### Installer Redis

**Windows (Docker — recommandé)**
```bash
docker run -d --name redis-agc -p 6379:6379 redis:alpine
```
**macOS** : `brew install redis && brew services start redis`
**Linux** : `sudo apt install redis-server && sudo systemctl start redis`

#### 1. Installer les dépendances Python

```bash
pip install django djangorestframework django-cors-headers \
    djangorestframework-simplejwt python-dotenv psycopg2-binary \
    django-redis gunicorn pytest pytest-django Pillow
```

#### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Remplir `.env` :

| Variable | Obligatoire | Comment l'obtenir |
|----------|-------------|-------------------|
| `SECRET_KEY` | ✅ | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `HMAC_SECRET_KEY` | ✅ | `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_PASSWORD` | ✅ | Mot de passe de votre utilisateur PostgreSQL |
| `DB_NAME` | — | `agc_space` (défaut) |
| `REDIS_URL` | — | `redis://localhost:6379/0` (défaut) |
| `DEBUG` | — | `True` en dev, `False` en prod |

#### 3. Créer la base PostgreSQL

```bash
psql -U postgres -c "CREATE DATABASE agc_space;"
```

#### 4. Migrations + seed

```bash
python manage.py migrate
python seed.py
```

Utilisateurs de test créés (mot de passe : `agcspace123`) :

| Username | Rôle |
|----------|------|
| `vendeur_test` | E-commerçant |
| `client_test` | Client |
| `affilie_test` | Affilié |

#### 5. Lancer le serveur

```bash
python manage.py runserver
```

API disponible sur **http://localhost:8000**

Vérification : `curl http://localhost:8000/health/`

#### 6. Tests backend

```bash
pytest
```

---

### Frontend (Next.js)

Temps estimé : **5 minutes** (après le backend)

#### Prérequis

| Outil | Version min | Obtenir |
|-------|-------------|---------|
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| npm | 9+ | Inclus avec Node.js |

#### 1. Installer les dépendances

```bash
cd frontend
npm install
```

#### 2. Configurer les variables d'environnement

```bash
cp .env.local.example .env.local
```

| Variable | Valeur par défaut | Description |
|----------|-------------------|-------------|
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | URL du backend Django |
| `NEXT_PUBLIC_AFFILIATION_COOKIE_DAYS` | `30` | Durée de vie du cookie d'affiliation |
| `NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY` | *(optionnel)* | Clé publique Stripe — obtenir sur [dashboard.stripe.com](https://dashboard.stripe.com/apikeys). Si absent, le checkout Stripe est désactivé. |

#### 3. Lancer le serveur de développement

```bash
npm run dev
```

Frontend disponible sur **http://localhost:3000**

#### 4. Tests frontend

```bash
# Tests unitaires (Vitest)
npm test

# Tests E2E Playwright (nécessite backend + frontend démarrés)
npx playwright install chromium   # première fois uniquement
npm run test:e2e

# Score Lighthouse (nécessite frontend démarré)
npm run lighthouse
```

#### 5. Build production

```bash
npm run build
npm start
```

---

### Déploiement production (VPS)

#### Backend

```bash
# Collecter les fichiers statiques
python manage.py collectstatic --noinput

# Copier les configs
sudo cp deploy/nginx.conf /etc/nginx/sites-available/agcspace
sudo ln -s /etc/nginx/sites-available/agcspace /etc/nginx/sites-enabled/
sudo cp deploy/agcspace.service /etc/systemd/system/

# Adapter les chemins dans les fichiers (votre-domaine.com)

# Activer
sudo systemctl enable agcspace && sudo systemctl start agcspace
sudo nginx -t && sudo systemctl reload nginx

# SSL
sudo certbot --nginx -d votre-domaine.com
```

#### Frontend (Next.js sur VPS)

```bash
cd frontend
npm run build

# Avec PM2
npm install -g pm2
pm2 start npm --name "agcspace-front" -- start
pm2 save && pm2 startup
```

Ajouter dans `deploy/nginx.conf` :
```nginx
location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

#### Variables `.env` à changer en production

**Backend `.env`**
```
DEBUG=False
SECRET_KEY=<clé-longue-unique>
```

---

## Migration V1 → V2 du Builder

### 5-Minute Setup

#### 1️⃣ Enable V2 (.env.local)
```bash
NEXT_PUBLIC_BUILDER_V2=true
```

#### 2️⃣ Restart Dev Server
```bash
npm run dev
```

#### 3️⃣ Test
Open: http://localhost:3000/dashboard/builder/1

Expected: "Builder V2 — Product Name" header ✅

---

### What Changed for Users

#### ❌ Before (V1)
- Sidebar: List of blocks (limited space)
- Preview: Separate panel, manual refresh
- Edit: Click block → properties sidebar (not inline)
- Actions: Only delete
- User reaction: "This feels like a PowerPoint from 2005"

#### ✅ After (V2)
- Layout: 50% editor | 50% live preview
- Edit: Click block → modal form (focus editing)
- Actions: Duplicate, Move up/down (drag & drop)
- Preview: Real-time sync (< 50ms)
- User reaction: "This feels like Shopify! 🤩"

---

### Key Differences for Developers

| Aspect | V1 | V2 |
|--------|----|----|
| Component | `BlockEditor` | `EnhancedBlockEditor` |
| Layout | `w-80 sidebar` | `40/40/20 split` |
| Edit UX | Sidebar form | Properties panel + inline |
| Preview | PageRenderer separate | Integrated in 3-panel layout |
| Logging | Minimal | Structured `logger.ts` |
| Tests | 28 tests | 53 tests (+25) |
| Fallback | None | V2 only (V1 removed) |

---

### File Structure

```
frontend/
├── src/modules/builder/
│   ├── logger.ts                  ← Structured logging (propertyChanged added)
│   ├── utils.ts                   ← Validation/Utils
│   ├── builder-utils.test.ts      ← Tests (10)
│   └── components/
│       ├── EnhancedBlockEditor.tsx ← V2 Editor (320 lines, PropertiesPanel integrated)
│       ├── BlockEditorForm.tsx    ← Inline form
│       ├── PropertiesPanel.tsx    ← NEW: Properties sidebar with tabs
│       ├── EnhancedBlockEditor.test.ts ← Tests (12)
│       ├── BlockEditorForm.test.ts    ← Tests (15)
│       ├── PropertiesPanel.test.tsx   ← NEW: Tests (11)
│       └── builder-utils.test.ts      ← Tests (10)
├── app/(dashboard)/dashboard/builder/
│   └── [productId]/page.tsx       ← V2 only (V1 removed)
├── .env.local.example             ← V2 vars
└── PHASE_F10.2_*                  ← Documentation updated

backend/
├── products/                      ← NO CHANGES (API stays same)
├── orders/                        ← NO CHANGES
└── ...
```

---

### Migration Status

**✅ F10.1 Completed**: V2 builder with integrated preview  
**✅ F10.2 Completed**: Properties panel with advanced editing  
**🔄 Ready for F10.3**: Enriched block types and performance optimizations

Builder V2 is now the only version. All V1 references have been removed, documentation consolidated, and the properties panel provides advanced editing capabilities with live preview sync.
# - Falls back to BlockEditor (V1)
# - Logs to console: "[Migration] fallbackToV1"
```

**Zero lines of backend code changed** ✅
| GET | `/api/v1/orders/` | Mes commandes | Oui |
| GET | `/api/v1/orders/<id>/` | Détail commande | Oui |
| GET | `/api/v1/orders/<id>/commission/` | Commission liée | Oui |

### Système

| Méthode | Endpoint | Description | Auth |
|---------|----------|-------------|------|
| GET | `/health/` | État DB + Redis | Non |
| GET | `/admin/` | Interface d'administration | Staff |

---

## Sécurité

- **JWT** : tokens courts (60min) avec rotation des refresh tokens
- **HMAC-SHA256** : liens d'affiliation infalsifiables, expiration 30 jours
- **Timing attack** : `hmac.compare_digest` sur toutes les comparaisons de signatures
- **ACID** : transactions atomiques sur les commandes — impossible d'avoir une commande sans commission ou vice-versa
- **Rate limiting** : 100 req/h anonyme, 1000 req/h authentifié (configurable)
- **HSTS + SSL redirect** : activés automatiquement en production (`DEBUG=False`)
- **Prix figés** : `unit_price` et `commission_rate` figés à l'achat — aucune modification rétroactive possible

---

## Tests

```bash
pytest                    # Tous les tests
pytest users/             # Tests d'une app
pytest -k "test_flow"     # Tests par nom
pytest -v --tb=short      # Mode verbeux
```

Couverture : 60+ tests répartis sur 5 modules.

| Module | Tests |
|--------|-------|
| `users/tests.py` | Modèles, multi-rôles, API auth JWT |
| `products/tests.py` | Produits, templates, Smart Builder, API rendu |
| `products/tests_cache.py` | Cache Redis, invalidation, health check |
| `affiliations/tests.py` | HMAC, commissions, flow validation |
| `orders/tests.py` | ACID atomique, stock, commissions, flow complet |

---

## Roadmap

| Phase | Statut |
|-------|--------|
| Phase 1 — Fondations (modèles, auth, API) | ✅ Terminée |
| Phase 2 — Smart Builder (thèmes, blocs, rendu) | ✅ Terminée |
| Phase 3 — Affiliation & tunnel de vente (HMAC, ACID) | ✅ Terminée |
| Phase 4 — Performance & déploiement (Redis, Nginx) | ✅ Terminée |
| Frontend React/Next.js | 🔲 À venir |

Voir `roadmap.md` pour le détail complet de chaque phase.

---

---

## Frontend (Next.js 14)

### Stack

| Composant | Technologie | Rôle |
|-----------|-------------|------|
| Framework | Next.js 14 App Router | SSR/ISR pour le SEO des pages de vente |
| Style | Tailwind CSS | Classes dynamiques depuis le JSON du builder |
| State | Zustand | Panier, auth, affiliation — stores persistés |
| Data fetching | TanStack Query | Cache, retries automatiques, états de chargement |
| Drag & Drop | dnd-kit | Builder de blocs |
| Tests | Vitest + Testing Library | Tests unitaires stores et composants |

### Architecture modules

```
frontend/
  app/                          ← Pages Next.js (App Router)
    (auth)/login|register/      ← Pages auth (SSR)
    (shop)/shop/[productId]/    ← Page de vente publique (SSR + ISR)
    (dashboard)/dashboard/      ← Back-office (Client Components)
    checkout/                   ← Tunnel de paiement
  src/
    modules/
      auth/                     ← service, store Zustand, composants
      renderer/                 ← ComponentMap + PageRenderer + blocs
      builder/                  ← BlockEditor drag & drop
      cart/                     ← store Zustand + CartDrawer
      affiliation/              ← store + AffiliationInit
      dashboard/                ← productService + pages
    lib/                        ← apiClient (axios + JWT refresh), utils, queryClient
    types/                      ← Types TypeScript globaux
    tests/                      ← Tests Vitest
```

### Moteur de rendu (PageRenderer)

Le `PageRenderer` est agnostique au contenu. Il boucle sur les blocs retournés par `/render/` et injecte le composant correspondant via le `COMPONENT_MAP` :

```typescript
const COMPONENT_MAP = {
  hero:         dynamic(() => import('./blocks/HeroBlock'),      { ssr: true }),
  social_proof: dynamic(() => import('./blocks/SocialProofBlock'), { ssr: false }),
  countdown:    dynamic(() => import('./blocks/CountdownBlock'),  { ssr: false }),
  buy_button:   dynamic(() => import('./blocks/BuyButtonBlock'),  { ssr: false }),
  // ...
}
```

Lazy loading par type — le code d'un `CountdownBlock` n'est pas chargé si le template n'en contient pas.

### Gestion du FOUC

Le `critical_css` retourné par le backend est injecté dans `<style>` avant le rendu des blocs. Zéro flash de contenu non stylé.

### Flow affiliation côté front

```
1. Visiteur arrive sur /shop/42/?ref=CODE&sig=HMAC&exp=TS
2. AffiliationInit appelle GET /affiliations/validate/
3. Si valide → cookie first-party agc_ref=CODE (SameSite=Lax)
4. BuyButtonBlock lit le cookie via useAffiliationStore
5. Checkout envoie { referral_code: CODE } → Commission créée côté backend
```

Protection tracking Safari/Chrome : cookie first-party posé via le backend Django, pas de cookie tiers.

### Builder drag & drop

`BlockEditor` utilise `dnd-kit` pour réordonner les blocs. L'auto-save est debounced à 800ms — l'API Django n'est appelée qu'une fois après la dernière modification, pas à chaque drag.

Le mode Live Preview affiche le `PageRenderer` en temps réel à gauche pendant que l'éditeur est à droite.

---

## Auteur

**Gilles** — Projet AGC Space
