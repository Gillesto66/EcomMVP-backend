# Analyse Technique — AGC Space (ecomMVP)
> Auteur de l'analyse : Kiro | Date : 19 avril 2026  
> Stack : Django 5.2 + DRF 3.16 | Next.js 14 + React 18 | PostgreSQL | Redis | Zustand

---

## Méthodologie de notation

Chaque système est noté sur **5** selon trois axes pondérés :
- **Efficacité** (fonctionnel, complet, sans friction) — 40 %
- **Sécurité** (protection des données, résistance aux attaques) — 35 %
- **Pertinence** (alignement avec l'objectif Shopify-killer) — 25 %

---

## 1. Authentification & Gestion des rôles

### Ce qui est fait
- Modèle `User` custom (AbstractUser) avec `ManyToMany` sur `Role`
- 3 rôles : `ecommercant`, `client`, `affilie` — cumulables sur un même compte
- JWT via SimpleJWT : access 60 min, refresh 7 jours, rotation activée
- Endpoints : register, login, refresh, me, change-password
- Intercepteur axios côté front : refresh automatique sur 401, redirect `/login` si refresh expiré
- Store Zustand persisté en localStorage avec `partialize` (seul `user` est sérialisé)
- `AuthInitializer` qui restaure la session au démarrage via `GET /auth/me/`

### Points forts
- Multi-rôles bien pensé : un affilié peut aussi être e-commerçant
- Refresh automatique transparent pour l'utilisateur
- `has_role()` propre et réutilisable dans les permissions DRF

### Ce qui manque pour 5/5
- **Blacklist JWT** : `BLACKLIST_AFTER_ROTATION = True` est activé mais `rest_framework_simplejwt.token_blacklist` n'est pas dans `INSTALLED_APPS` → la blacklist ne fonctionne pas réellement
- **Pas d'endpoint logout** côté backend : le refresh token n'est pas invalidé côté serveur à la déconnexion (seulement supprimé du localStorage)
- **Tokens en localStorage** : vulnérable aux attaques XSS. Les tokens devraient être en cookies `HttpOnly`
- **Pas de vérification email** : un compte peut être créé avec n'importe quelle adresse sans confirmation
- **Pas de rate limiting spécifique** sur `/auth/login/` (brute force possible malgré le throttle global)
- **Pas de 2FA** (acceptable pour un MVP, mais à noter)

### Note : **3.5 / 5**

---

## 2. Marketplace & Gestion des produits

### Ce qui est fait
- Modèle `Product` complet : SKU indexé, stock, digital/physique, 3 images, catégorie, `views_count`
- Auto-génération du SKU si absent (`AGC-{uuid[:8]}`)
- `IsOwnerOrReadOnly` : seul le propriétaire peut modifier son produit
- Endpoint public `GET /render/<id>/` pour les pages de vente
- `views_count` incrémenté à chaque rendu via `F()` expression (sans race condition)
- Serializer avec URLs absolues pour les images
- `VendeurStatsView` : CA, produits actifs, affiliés actifs, taux moyen, top produit

### Points forts
- Séparation propre entre lecture publique et écriture propriétaire
- `views_count` avec `F()` : bonne pratique pour les compteurs concurrents
- Stats vendeur complètes et utiles pour le dashboard

### Ce qui manque pour 5/5
- **Pas de pagination** sur `GET /products/` : avec 1000 produits, la réponse sera énorme
- **Pas de recherche / filtrage** : impossible de filtrer par catégorie, prix, ou rechercher par nom
- **Pas de variantes produits** : taille, couleur, etc. (gap majeur vs Shopify)
- **Pas de promotions / coupons** : aucun système de réduction
- **Upload d'images non sécurisé** : `FileUploadView` utilise `python-magic` et `moviepy` qui ne sont pas dans les dépendances listées, et le chemin temporaire `/tmp/temp_video_{user_id}_{filename}` est prévisible (risque path traversal)
- **Pas de CDN** pour les médias : les images sont servies directement par Nginx
- **Pas de validation de la taille des images** côté backend (seulement côté front)
- **`is_active=True` par défaut** : un produit est public dès sa création sans validation

### Note : **3 / 5**

---

## 3. Smart Builder (Page de vente)

### Ce qui est fait
- `PageTemplate` avec config JSON validée (types de blocs, structure `visibility`)
- 13 types de blocs valides dont les "conversion-ready" : `social_proof`, `countdown`, `stock_status`, `buy_button`
- Visibilité conditionnelle par stock (`stock_min`, `stock_max`)
- Critical CSS généré automatiquement au `save()` du template (lazy par type de bloc)
- Endpoint `/render/` retourne un payload complet : produit + thème + blocs enrichis + CSS
- `enrich_blocks()` injecte les données dynamiques (ventes réelles, countdown, stock)
- Builder V2 côté front : layout 50/50, preview live < 50ms, drag & drop dnd-kit, auto-save debounced 800ms
- `BuilderInitView` crée un template par défaut si le produit n'en a pas
- Templates réutilisables entre produits (`is_public`)

### Points forts
- Architecture payload unique `/render/` : le front n'a qu'un seul appel à faire
- Critical CSS injection : zéro FOUC, zéro calcul au rendu
- `social_proof` basé sur des vraies données de vente (pas du fake)
- Countdown basé sur `created_at` : simple mais fonctionnel

### Ce qui manque pour 5/5
- **Countdown non configurable** : basé sur `created_at + duration_hours`, pas sur une vraie date de fin définie par le vendeur
- **Pas d'undo/redo persistant** : l'undo/redo est en mémoire, perdu au rechargement
- **Pas de templates prédéfinis** (galerie de templates) : le vendeur part de zéro
- **Pas de blocs avancés** : pas de formulaire de capture email, pas de vidéo YouTube embed natif, pas de tableau de prix
- **Pas de SEO** : pas de meta title/description configurables par produit dans le builder
- **Pas de mobile preview** dans le builder : on ne sait pas comment la page rend sur mobile
- **`FileUploadView` cassée** : dépendances `python-magic` et `moviepy` absentes des requirements
- **Un seul template actif par produit** : pas de A/B testing possible
- **Pas de sauvegarde automatique** côté backend (seulement debounce front)

### Note : **3.5 / 5**

---

## 4. Système d'affiliation

### Ce qui est fait
- `AffiliationLink` avec `tracking_code` unique (`secrets.token_urlsafe(16)`)
- Signature HMAC-SHA256 sur `tracking_code:product_id:expires_at`
- Protection timing attack : `hmac.compare_digest`
- Expiration 30 jours configurable
- Validation côté backend avant de poser le cookie
- Cookie first-party `agc_ref` (SameSite=Lax) : résistant aux restrictions Safari/Chrome
- `Commission` créée atomiquement avec la commande (ACID garanti)
- Taux et montant figés au moment de la vente
- Statuts de commission : `pending → validated → paid / cancelled`
- Stats affilié : gains, commissions en attente, taux de conversion
- Marketplace affilié : liste des produits disponibles avec lien existant
- Tests HMAC complets : falsification product_id, expiration, mauvaise signature

### Points forts
- HMAC-SHA256 avec expiration : impossible de falsifier le taux ou le produit
- `hmac.compare_digest` : protection timing attack correctement implémentée
- Cookie first-party : contourne les restrictions ITP de Safari
- Taux figé : intégrité comptable garantie même si le vendeur change le taux après

### Ce qui manque pour 5/5
- **Pas de validation du taux de commission** : un affilié peut créer un lien avec `commission_rate = 0.9999` (99.99%) sans aucune limite
- **Pas de plafond de commission** défini par le vendeur : le vendeur ne contrôle pas le taux que l'affilié se fixe
- **Cookie `HttpOnly: False`** : le cookie est lisible par JavaScript, exposé aux XSS
- **Pas de tracking des clics** : on ne sait pas combien de fois un lien a été cliqué (seulement les conversions)
- **Pas de délai de rétractation automatique** : les commissions passent en `pending` mais rien n'automatise la validation après X jours
- **Pas de paiement automatique** des affiliés : le versement est manuel via l'admin Django
- **`hmac_signature` stocké en base** : c'est un cache de la dernière signature, mais cela pourrait induire en erreur (la signature change à chaque appel)
- **Pas de protection contre l'auto-affiliation** : un vendeur peut créer un lien affilié sur son propre produit

### Note : **3.5 / 5**

---

## 5. Système de commandes (ACID)

### Ce qui est fait
- `create_order_atomic()` avec `@transaction.atomic` : rollback complet si une étape échoue
- Vérification stock avant création de la commande
- `F()` expression pour le décrément du stock : pas de race condition
- Prix figés (`unit_price`) à l'achat
- Produits digitaux : stock non décrémenté
- Referral code invalide : vente continue sans commission (pas de blocage)
- Tests d'intégration complets : flow complet, rollback stock, taux figé, digital vs physique
- `OrderItem.subtotal` calculé en `Decimal` (pas de float)

### Points forts
- Transaction atomique bien structurée avec séparation des responsabilités
- `F()` pour le stock : la seule bonne façon de faire en Django concurrent
- Tests d'intégration qui couvrent les cas limites (stock insuffisant, code invalide)
- Prix en `Decimal` partout : pas d'erreurs d'arrondi

### Ce qui manque pour 5/5
- **Pas de paiement réel** : le statut reste `pending` indéfiniment, aucune intégration Stripe/PayPal complète côté backend
- **Pas de webhook Stripe** : même si Stripe est mentionné côté front, le backend ne traite pas les événements de paiement
- **Pas de confirmation de commande par email** : le client ne reçoit rien après l'achat
- **Pas de gestion des remboursements** : le statut `refunded` existe mais aucune logique associée
- **Pas de numéro de commande lisible** : seulement l'ID auto-incrémenté (pas de `ORD-2026-0001`)
- **Pas de TVA / taxes** : aucun calcul de taxe
- **Pas de livraison** : aucun système d'adresse ou de frais de port pour les produits physiques
- **Commande multi-vendeurs non gérée** : si le panier contient des produits de 2 vendeurs différents, une seule commande est créée (problème comptable)

### Note : **3 / 5**

---

## 6. Panier & Checkout (Frontend)

### Ce qui est fait
- Store Zustand persisté en localStorage (`agc-cart`)
- `addItem`, `removeItem`, `updateQuantity`, `clearCart`
- `totalItems()` et `totalPrice()` calculés à la volée
- `CartDrawer` avec overlay, modification quantités, affichage du tracking affilié actif
- `checkout()` envoie le `referral_code` si présent
- Gestion des erreurs avec retry possible
- `lastOrder` stocké après achat pour la page de succès
- Événement custom `agc:open-cart` pour ouvrir le drawer depuis n'importe quel composant

### Points forts
- Persistance localStorage : le panier survit au rechargement
- Intégration affiliation transparente : le `trackingCode` est lu depuis le store
- Architecture événementielle propre pour l'ouverture du drawer

### Ce qui manque pour 5/5
- **Pas de synchronisation avec le stock en temps réel** : on peut ajouter au panier un produit en rupture de stock
- **Pas de validation des quantités** : on peut mettre une quantité négative ou 0 (le `removeItem` est appelé mais seulement si `quantity <= 0`)
- **Pas de page checkout complète** : la page `/checkout` existe mais l'intégration Stripe n'est que partielle (bouton présent, pas de webhook backend)
- **Prix calculé côté front** : `totalPrice()` utilise `product.price` du store, pas le prix validé par le backend (risque de désynchronisation si le prix change)
- **Pas de gestion des produits indisponibles** dans le panier : si un produit est désactivé entre l'ajout et le checkout, l'erreur backend n'est pas bien gérée
- **Pas de sauvegarde du panier côté serveur** : si l'utilisateur change de navigateur, le panier est perdu

### Note : **2.5 / 5**

---

## 7. Dashboard Vendeur

### Ce qui est fait
- `VendeurStatsView` : CA total, produits actifs, affiliés actifs, taux moyen, gain affilié, top produit
- `ProductForm` : création/édition avec images, SKU auto, catégorie, stock, digital/physique
- `ThemeEditor` : color picker + preview live + CSS généré visible
- `BuilderInitView` : crée un template par défaut si absent
- Pages dashboard : produits, commandes, affiliations, thème, builder

### Points forts
- Stats vendeur pertinentes et bien calculées
- ThemeEditor avec preview live en temps réel (applique les variables CSS sur `:root`)
- ProductForm avec validation côté front et gestion des images

### Ce qui manque pour 5/5
- **Pas d'analytics** : pas de graphiques de ventes dans le temps, pas de courbe de CA
- **Pas de gestion des commandes vendeur** : le vendeur ne peut pas voir les commandes de ses produits (seulement les stats globales)
- **Pas de gestion des affiliés** : le vendeur ne peut pas voir qui sont ses affiliés, ni valider/refuser des demandes d'affiliation
- **Pas de validation des commissions** depuis le dashboard : le vendeur doit passer par l'admin Django
- **Pas de notifications** : aucune alerte pour une nouvelle vente, une nouvelle commission, un stock bas
- **Pas de gestion multi-produits en masse** : pas de bulk edit, pas d'import CSV
- **Dashboard affilié incomplet** : les stats existent en API mais l'interface frontend est minimale
- **Pas de page de profil vendeur** : pas de personnalisation du nom de boutique, logo, etc.

### Note : **2.5 / 5**

---

## 8. Performance & Infrastructure

### Ce qui est fait
- Cache Redis : `/render/` 5 min, thèmes 1h, invalidation automatique au save()
- `IGNORE_EXCEPTIONS=True` : l'app continue si Redis est down
- Index PostgreSQL : GIN JSONB sur `config` et `variables`, index partiel sur `tracking_code` et `referral_code`
- `CONN_MAX_AGE=60` : connexions persistantes PostgreSQL
- Nginx : SSL/TLS, HSTS, headers sécurité, cache 1 min sur `/render/`, gzip
- Gunicorn : workers = CPU×2+1, timeout 30s
- Logs rotatifs : 10 MB × 5 fichiers
- Health check `/health/` : vérifie DB + Redis
- PWA : manifest + service worker
- Lazy loading des blocs React avec `dynamic()`

### Points forts
- Double cache (Redis + Nginx) sur l'endpoint le plus sollicité
- Invalidation cache correctement chaînée (produit → template → thème)
- Index GIN JSONB : requêtes sur les blocs JSON performantes
- Fallback Redis gracieux : pas de crash si Redis est indisponible

### Ce qui manque pour 5/5
- **Pas de rate limiting par IP** sur les endpoints sensibles (login, register, validate)
- **Pas de CDN** pour les assets statiques et médias
- **Pas de compression gzip** configurée côté Django (seulement Nginx)
- **Pas de monitoring** : pas de Sentry, pas de métriques Prometheus/Grafana
- **Pas de backup automatique** de la base de données
- **`proxy_cache_valid`** dans Nginx est configuré mais `proxy_cache_path` n'est pas défini → le cache Nginx ne fonctionne pas réellement
- **Pas de Content Security Policy (CSP)** dans les headers Nginx
- **Pas de tests de charge** : on ne sait pas combien de requêtes simultanées le système peut absorber

### Note : **3.5 / 5**

---

## 9. Tests

### Ce qui est fait
- 60+ tests répartis sur 5 modules
- Tests unitaires : modèles, serializers, services
- Tests d'intégration : flows complets (affiliation, ACID, rendu)
- `conftest.py` avec fixtures partagées et cache vidé entre chaque test
- `settings_test.py` avec SQLite en mémoire (tests rapides sans PostgreSQL)
- Tests HMAC : falsification, expiration, timing attack
- Tests ACID : rollback stock, taux figé, digital vs physique
- Tests frontend : Vitest + Testing Library (53 tests builder)
- Tests E2E : Playwright (flow affiliation)

### Points forts
- Tests d'intégration du flow complet affiliation → commande → commission
- Tests des cas limites (stock insuffisant, code invalide, produit inactif)
- Fixtures bien organisées et réutilisables

### Ce qui manque pour 5/5
- **Pas de mesure de couverture** : `.coverage` existe mais pas de rapport de couverture dans le CI
- **Pas de tests pour `FileUploadView`** : la vue la plus complexe n'est pas testée
- **Pas de tests pour `VendeurStatsView`** : les calculs de stats ne sont pas testés
- **Pas de tests pour `BuilderInitView`** : la création automatique de template n'est pas testée
- **Pas de CI/CD** : pas de GitHub Actions ou équivalent pour lancer les tests automatiquement
- **Tests frontend insuffisants** : pas de tests pour les stores Zustand (cart, auth, affiliation)
- **Pas de tests de sécurité** : pas de tests pour les injections, les accès non autorisés entre vendeurs

### Note : **3 / 5**

---

## Récapitulatif des notes

| Système | Note | Statut |
|---------|------|--------|
| 1. Authentification & Rôles | **3.5 / 5** | ⚠️ Solide mais tokens en localStorage |
| 2. Marketplace & Produits | **3 / 5** | ⚠️ Manque pagination, filtres, variantes |
| 3. Smart Builder | **3.5 / 5** | ⚠️ Bon moteur, manque templates & SEO |
| 4. Affiliation HMAC | **3.5 / 5** | ✅ Sécurité solide, manque contrôle vendeur |
| 5. Commandes ACID | **3 / 5** | ⚠️ Logique solide, manque paiement réel |
| 6. Panier & Checkout | **2.5 / 5** | ❌ Checkout incomplet, pas de Stripe backend |
| 7. Dashboard Vendeur | **2.5 / 5** | ❌ Manque analytics, gestion commandes |
| 8. Performance & Infra | **3.5 / 5** | ⚠️ Bonne base, cache Nginx non fonctionnel |
| 9. Tests | **3 / 5** | ⚠️ Bonne couverture métier, manque CI/CD |

**Moyenne globale : 3.1 / 5**

---

## Priorités pour atteindre 5/5

### 🔴 Critique (bloquant pour la production)

1. **Intégration Stripe complète** — webhook backend pour passer les commandes en `paid`
2. **Tokens JWT en cookies HttpOnly** — supprimer le localStorage pour les tokens
3. **Ajouter `rest_framework_simplejwt.token_blacklist`** dans `INSTALLED_APPS` + endpoint logout backend
4. **Limiter le taux de commission** — le vendeur doit définir un taux max, l'affilié ne peut pas dépasser
5. **Corriger le cache Nginx** — ajouter `proxy_cache_path` dans la config Nginx
6. **Supprimer les dépendances manquantes** (`python-magic`, `moviepy`) ou les ajouter aux requirements

### 🟠 Important (qualité produit)

7. **Pagination + filtres** sur `GET /products/` (django-filter)
8. **Email de confirmation** après inscription et après achat
9. **Gestion des commandes vendeur** — le vendeur doit voir les commandes de ses produits
10. **Validation des commissions** depuis le dashboard (pas seulement l'admin Django)
11. **Analytics vendeur** — graphique CA dans le temps (Chart.js ou Recharts)
12. **Notifications** — nouvelle vente, stock bas, commission validée
13. **CSP header** dans Nginx
14. **CI/CD** — GitHub Actions pour lancer pytest + vitest à chaque push

### 🟡 Améliorations (différenciation Shopify)

15. **Variantes produits** — taille, couleur, etc.
16. **Promotions / coupons** — codes de réduction
17. **Templates prédéfinis** — galerie de templates pour le builder
18. **SEO par produit** — meta title, description, og:image configurables
19. **Mobile preview** dans le builder
20. **A/B testing** — deux templates actifs avec répartition du trafic
21. **Délai de rétractation automatique** — validation automatique des commissions après X jours
22. **Protection anti-auto-affiliation** — un vendeur ne peut pas s'affilier à ses propres produits
23. **Tracking des clics** sur les liens d'affiliation
24. **Monitoring** — Sentry pour les erreurs, métriques de performance
