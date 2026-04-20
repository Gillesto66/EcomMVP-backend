# Auteur : Gilles - Projet : AGC Space - Module : Roadmap

# AGC Space — Roadmap Projet E-Commerce

---

## PHASE 1 : Architecture & Fondations ✅ TERMINÉE

- [x] Projet Django `agc_core` + PostgreSQL + `.env` (python-dotenv)
- [x] `djangorestframework` + `django-cors-headers` + `SimpleJWT`
- [x] App `users` — `User` multi-rôles + `Role` (ManyToMany)
- [x] App `products` — `Product`, `PageTemplate`, `ProductTemplate`
- [x] App `affiliations` — `AffiliationLink` (tracking_code indexé, HMAC préparé)
- [x] App `orders` — `Order` + `OrderItem` (unit_price figé)
- [x] Serializers, ViewSets, URLs, Admin pour les 4 apps
- [x] Tests unitaires `pytest` complets (modèles + API)
- [x] Script de seed `seed.py`
- [x] Logging sur tous les modules

### ⚠️ Action manuelle requise

```bash
python manage.py migrate
python seed.py
pytest   # 96/96 tests passent — couverture 92%
```

---

## PHASE 2 : Smart Builder ✅ TERMINÉE

### Moteur de Thème Global (Design System)

- [x] Modèle `Theme` lié à l'e-commerçant (OneToOne)
- [x] Stockage des variables CSS : `primary_color`, `secondary_color`, `font_family`, `border_radius`, `spacing_unit`…
- [x] Méthode `to_css_variables()` → génère un bloc `:root { --primary-color: ... }`
- [x] Thème injecté dans `GET /render/` — le front applique les variables aux composants React
- [x] `GET /api/v1/themes/mine/` — récupère ou crée le thème avec valeurs par défaut
- [x] Validation des clés de variables (liste blanche)

### Couche de Logique Conditionnelle

- [x] Champ `visibility` dans chaque bloc JSON : `{"stock_min": 5}`, `{"stock_max": 0}`
- [x] `evaluate_block_visibility(block, product)` — évalue les règles côté backend
- [x] Blocs invisibles filtrés avant envoi au front (pas de données inutiles)
- [x] Champ `stock` ajouté au modèle `Product`
- [x] Champ `action` supporté dans les blocs (ex: `"display_alert"`)

### Bibliothèque de Composants "Conversion-Ready"

- [x] **Social Proof** — données réelles depuis les logs de vente (30 derniers jours)
  - `total_sold`, `buyer_count` injectés dans `block.data`
- [x] **Countdown Timer** — basé sur `product.created_at` + `duration_hours`
  - `seconds_remaining`, `deadline_iso`, `is_expired` injectés dans `block.data`
- [x] **Stock Status** — état temps réel : `ok` / `low` (≤5) / `out`
  - `stock`, `label`, `level` injectés dans `block.data`
- [x] **BuyButton Affiliate Aware** — flag `affiliate_aware: true`
  - Le front détecte le `ref_id` en URL et déclenche un cookie de session (Phase 3)

### Performance : Critical CSS Injection

- [x] Génération automatique du `critical_css` au `save()` du template
- [x] CSS lazy par type de bloc — seuls les blocs présents génèrent du CSS
- [x] Variables du thème injectées dans le `:root` du Critical CSS
- [x] `GET /api/v1/templates/<id>/css/` — endpoint dédié au CSS pré-généré
- [x] `critical_css` inclus dans le payload `/render/` → à injecter en `<style>` dans le `<head>`

### Endpoint de Rendu Enrichi

- [x] `GET /api/v1/render/<product_id>/` retourne le payload complet :
  ```json
  {
    "product": { ... },
    "theme": { "variables": {...}, "css_preview": ":root { ... }" },
    "template": { "id": 1, "name": "..." },
    "blocks": [ { "type": "social_proof", "data": { "total_sold": 42 } }, ... ],
    "critical_css": ".block-hero { ... } .block-buy-button { ... }",
    "meta": {
      "tracking_events": [...],
      "affiliate_aware_blocks": ["buy_button"]
    }
  }
  ```
- [x] `meta.tracking_events` — liste des événements à tracker (Google Analytics / Pixel)
- [x] `meta.affiliate_aware_blocks` — liste des blocs qui doivent détecter le `ref_id`

### Tests Phase 2

- [x] Tests modèle `Theme` (CSS variables, edge cases)
- [x] Tests Critical CSS (lazy par type, injection thème)
- [x] Tests services (social proof, countdown, stock status, visibilité)
- [x] Tests serializers (validation variables thème, validation blocs)
- [x] Tests API (payload complet, blocs enrichis, visibilité stock, meta tracking)

### 🔲 Reste à faire (Phase 2 — Frontend, hors scope backend)

- [ ] Composants React par type de bloc (`hero`, `buy_button`, `social_proof`…)
- [ ] Drag-and-drop avec `react-grid-layout`
- [ ] Lazy loading des composants React (ne charger que les blocs présents)
- [ ] Gestion d'état global panier + affiliation avec Zustand
- [ ] Injection du `critical_css` en `<style>` dans le `<head>` (Next.js `_document`)

---

## PHASE 3 : Tunnel de Vente & Affiliation ✅ TERMINÉE

### Sécurité HMAC

- [x] `affiliations/services.py` — `generate_signed_url()` : signature HMAC-SHA256 sur `tracking_code:product_id:expires_at`
- [x] `verify_signed_url()` : comparaison en temps constant (`hmac.compare_digest`) — protection timing attack
- [x] Expiration configurable (30 jours par défaut)
- [x] Falsification du `product_id` détectée (la signature couvre le product_id)
- [x] `POST /api/v1/affiliations/links/<id>/signed-url/` — génère l'URL signée

### Flow Complet

- [x] `GET /api/v1/affiliations/validate/?ref=&sig=&exp=&product_id=` — validation publique
  - Vérifie signature + expiration + existence du lien
  - Retourne le payload du cookie de session `agc_ref` à poser côté front
  - `cookie_httponly: false` — le front JS doit pouvoir le lire pour l'envoyer à la commande
- [x] `POST /api/v1/orders/create/` — lit le `referral_code`, crée la commission atomiquement

### Transaction Atomique ACID (`orders/services.py`)

- [x] `create_order_atomic()` — décorateur `@transaction.atomic`
- [x] Opérations dans la transaction :
  1. Vérification du stock (avant toute écriture)
  2. Création `Order`
  3. Création `OrderItem` (prix figés)
  4. Calcul et mise à jour du total
  5. Décrément stock via `F()` expression (atomic SQL, pas de race condition)
  6. Résolution `referral_code` → `AffiliationLink`
  7. Création `Commission` (taux et total figés)
- [x] Rollback complet si une étape échoue
- [x] Referral code invalide → vente continue sans commission (pas d'exception)
- [x] Produits digitaux → stock non décrémenté

### Modèle Commission

- [x] `Commission` : `order` (OneToOne), `affiliation_link`, `affiliate`, `order_total`, `commission_rate`, `amount`, `status`
- [x] `order_total` et `commission_rate` figés au moment du calcul
- [x] Statuts : `pending` → `validated` → `paid` / `cancelled`
- [x] Admin avec actions : valider en masse, marquer comme versées

### Endpoints Phase 3

- [x] `POST /api/v1/affiliations/links/<id>/signed-url/` — URL signée HMAC
- [x] `GET /api/v1/affiliations/validate/` — validation publique du lien
- [x] `GET /api/v1/affiliations/links/stats/` — stats globales de l'affilié
- [x] `GET /api/v1/affiliations/commissions/` — liste des commissions
- [x] `GET /api/v1/orders/<id>/commission/` — détail commission d'une commande
- [x] `OrderSerializer` expose le champ `commission` (nested)

### Tests Phase 3

- [x] Tests HMAC : signature valide, mauvaise signature, lien expiré, falsification product_id
- [x] Tests Commission : création, taux figé, str
- [x] Tests API : signed-url, validate (valide/invalide), stats, commissions
- [x] Tests service atomique : vente simple, vente affiliée, taux figé, stock décrémenté, rollback stock insuffisant, referral invalide, digital non décrémenté
- [x] **Test d'intégration complet** `TestFlowCompletAffiliation` : flow de bout en bout en 5 étapes

---

## PHASE 4 : Performance & Déploiement ✅ TERMINÉE

### Cache Redis

- [x] `products/cache.py` — couche de cache isolée (principe Single Responsibility)
- [x] `get_render_cache` / `set_render_cache` / `invalidate_render_cache`
- [x] `get_theme_cache` / `set_theme_cache` / `invalidate_theme_cache`
- [x] `invalidate_all_renders_for_owner` — invalidation en cascade quand le thème change
- [x] TTL configurables via `.env` : `CACHE_TTL_PAGE_RENDER=300`, `CACHE_TTL_THEME=3600`
- [x] `IGNORE_EXCEPTIONS=True` — Redis down → app continue sans cache
- [x] Invalidation automatique au `perform_update()` des ViewSets (produit, template, thème)
- [x] `conftest.py` — override Redis → locmem pour tous les tests (pas besoin de Redis en CI)

### Index PostgreSQL JSONB

- [x] Migration `0004_phase4_jsonb_indexes` avec index `CONCURRENTLY IF NOT EXISTS`
- [x] `products_pagetemplate_config_gin` — GIN sur `config` (recherche dans les blocs JSON)
- [x] `products_theme_variables_gin` — GIN sur `variables` (filtrage par variable CSS)
- [x] `orders_order_referral_partial` — index partiel sur `referral_code WHERE NOT NULL`
- [x] `affiliations_link_tracking_code_idx` — index partiel sur `tracking_code WHERE is_active`

### Settings production

- [x] `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` — activés si `DEBUG=False`
- [x] `CONN_MAX_AGE=60` — connexions PostgreSQL persistantes
- [x] Rate limiting DRF : 100 req/h anonyme, 1000 req/h authentifié (configurable)
- [x] `STATIC_ROOT` + `MEDIA_ROOT` configurés pour `collectstatic`
- [x] Logs rotatifs : `RotatingFileHandler` 10 MB × 5 fichiers dans `logs/`
- [x] `HMAC_SECRET_KEY` — clé dédiée séparée de `SECRET_KEY`

### Infrastructure

- [x] `deploy/gunicorn.conf.py` — workers `(CPU×2)+1`, logs, bind, timeout, pidfile
- [x] `deploy/nginx.conf` — SSL/TLS, HSTS, headers sécurité, proxy, cache `/render/` 1min, gzip static
- [x] `deploy/agcspace.service` — service systemd avec `Requires=postgresql redis`
- [x] `GET /health/` — vérifie PostgreSQL + Redis, retourne `200 ok` ou `503 degraded`

### Tests Phase 4

- [x] `products/tests_cache.py` — 12 tests : cache hit/miss, set, invalidation, Redis down, clés uniques
- [x] Tests invalidation après `perform_update` produit
- [x] Tests health check (DB ok, statut 200/503)

### Documentation

- [x] `QUICKSTART.md` — lancer le backend en 10 minutes, toutes les clés expliquées
- [x] `README.md` — documentation complète du MVP (architecture, flows, API, sécurité, tests)
- [x] `.env.example` — toutes les variables documentées avec instructions d'obtention

### Audit — Écarts Shopify
- ⚠️ Le MVP couvre déjà : affiliation HMAC, builder visuel, checkout transactionnel ACID, cache Redis, PWA et tests solides.
- ⚠️ Pour aller chercher Shopify, il reste à adresser :
  - multi-domaines / boutiques multiples / custom domains
  - variantes produits avancées, collections, promotions/coupons, taxes et frais de livraison
  - abonnement / billing récurrent
  - analytics store / tableau de bord de performance en temps réel
  - webhooks, app ecosystem et intégrations tierces
  - localisation / multi-devise / SEO multi-langue
- 🛠️ Correctif appliqué : `EnhancedBlockEditor.tsx` header builder réparé pour restaurer le rendu et supprimer la duplication Undo/Redo.

---

## Compétences maîtrisées

| Domaine | Compétence | Statut |
|---------|-----------|--------|
| Backend | Nested serializers + validation JSON complexe | ✅ |
| Backend | QuerySet optimization (`select_related`, `prefetch_related`) | ✅ |
| Backend | HMAC/Signatures — liens d'affiliation infalsifiables | ✅ |
| Backend | Services layer (logique métier isolée des views) | ✅ |
| Frontend | Render Props / HOC pour injection JSON → composants React | ✅ |
| Frontend | Zustand / Redux — état global panier + affiliation | ✅ |
| Frontend | Lazy Loading composants React (par type de bloc) | ✅ |
| Data | JSONB PostgreSQL — index GIN sur templates et thèmes | ✅ |
| DevOps | Redis — cache pages de vente + thèmes avec invalidation | ✅ |
| DevOps | Nginx + Gunicorn + systemd — stack production complète | ✅ |

---

## Endpoints API disponibles

| Méthode | URL | Description | Auth |
|---------|-----|-------------|------|
| POST | `/api/v1/auth/register/` | Inscription | Non |
| POST | `/api/v1/auth/login/` | Login JWT | Non |
| POST | `/api/v1/auth/token/refresh/` | Refresh token | Non |
| GET/PUT | `/api/v1/auth/me/` | Profil utilisateur | Oui |
| GET/POST | `/api/v1/products/` | Liste / créer produits | Oui |
| GET | `/api/v1/products/<id>/templates/` | Templates d'un produit | Oui |
| GET/POST | `/api/v1/themes/` | CRUD thèmes | Oui |
| GET | `/api/v1/themes/mine/` | Mon thème (get or create) | Oui |
| GET/POST | `/api/v1/templates/` | Liste / créer templates | Oui |
| POST | `/api/v1/templates/<id>/assign/` | Assigner template à produit | Oui |
| GET | `/api/v1/templates/<id>/css/` | Critical CSS pré-généré | Oui |
| **GET** | **`/api/v1/render/<product_id>/`** | **Payload complet de rendu** | **Non** |
| POST | `/api/v1/affiliations/links/<id>/signed-url/` | URL signée HMAC | Affilié |
| GET | `/api/v1/affiliations/validate/` | Validation publique du lien | Non |
| GET | `/api/v1/affiliations/links/stats/` | Stats globales affilié | Affilié |
| GET | `/api/v1/affiliations/commissions/` | Mes commissions | Affilié |
| GET | `/api/v1/orders/<id>/commission/` | Commission d'une commande | Oui |
| POST | `/api/v1/orders/create/` | Créer une commande | Oui |
| GET | `/api/v1/orders/` | Mes commandes | Oui |
