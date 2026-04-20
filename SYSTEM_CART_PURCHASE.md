# 🛒 Système de Panier & Achat — Documentation Complète

Auteur : Gilles | Projet : AGC Space | Date : 19 avril 2026

## 📋 Vue d'ensemble du système

Le système de panier et d'achat est composé de:

1. **Frontend** (Next.js):
   - Store Zustand (`cartStore`) pour gérer l'état du panier
   - Composants UI (`CartDrawer`, `BuyButtonBlock`)
   - Page de checkout (`/checkout`)
   - Gestion de l'affiliation (tracking codes)

2. **Backend** (Django):
   - Models: `Order`, `OrderItem`
   - Sérializers: validation et création
   - Views: endpoints CRUD
   - Services: logique métier atomique

3. **Persistance**:
   - Panier: localStorage via Zustand persist middleware
   - Utilisateur: localStorage (tokens) + Zustand store
   - Session: auto-restore au rechargement

---

## 🏗️ Architecture détaillée

### Frontend: Zustand Cart Store

```
frontend/src/modules/cart/store/cartStore.ts
├─ State
│  ├─ items: CartItem[]          // [{ product, quantity }, ...]
│  ├─ isOpen: boolean            // Affichage du drawer
│  ├─ isCheckingOut: boolean     // Flag paiement en cours
│  ├─ lastOrder: Order | null    // Dernière commande créée
│  └─ error: string | null       // Messages d'erreur
├─ Actions
│  ├─ addItem(product, quantity) // Ajouter au panier
│  ├─ removeItem(productId)      // Supprimer du panier
│  ├─ updateQuantity()           // Modifier quantité
│  ├─ clearCart()                // Vider le panier
│  ├─ openCart() / closeCart()   // UI drawer
│  └─ checkout(referralCode?)    // Créer commande (POST /orders/create/)
└─ Computed
   ├─ totalItems()               // Nombre d'articles
   └─ totalPrice()               // Montant total
```

### Backend: Modèles & Logique

#### Order (Commande)
```python
Order
├─ customer: ForeignKey(User)         # Client
├─ referral_code: str (nullable)      # Code tracking affilié
├─ status: ['pending', 'paid', 'cancelled', 'refunded']
├─ total: Decimal                     # Montant total
├─ items: OrderItem[] (OneToMany)     # Lignes
├─ commission: Commission (OneToOne)  # Frais affilié (si applicable)
└─ timestamps: created_at, updated_at
```

#### OrderItem (Ligne de commande)
```python
OrderItem
├─ order: ForeignKey(Order)
├─ product: ForeignKey(Product)      # Produit commandé
├─ quantity: int                      # Quantité
├─ unit_price: Decimal (frozen)       # Prix au moment de la commande
└─ subtotal: Decimal (calculé)        # quantity × unit_price
```

---

## 🔄 Flux utilisateur complet

### 1️⃣ Ajout au panier

```
User clique sur BuyButtonBlock
    ↓
cartStore.addItem(product)
    ├─ Si product existe: increment quantity
    └─ Sinon: ajouter new CartItem
    ↓
localStorage['agc-cart'] = { items: [...] }
```

### 2️⃣ Affichage du panier

```
User clique "Voir le panier"
    ↓
CartDrawer s'affiche avec items
    ├─ Affiche les produits
    ├─ Permet modifier les quantités
    └─ Bouton "Passer la commande"
    ↓
User click "Passer la commande"
    └─ Redirection vers /checkout
```

### 3️⃣ Checkout (Récapitulatif)

```
Page /checkout
├─ Vérifier: user authentifié? (sinon → /login)
├─ Vérifier: panier non vide? (sinon → /)
├─ Afficher:
│  ├─ Récapitulatif des items
│  ├─ Total
│  ├─ Info affiliation (si trackingCode)
│  └─ Bouton paiement (Stripe ou direct)
```

### 4️⃣ Création de commande

```
User clique "Confirmer la commande"
    ↓
cartStore.checkout(referralCode?)
    ↓
POST /api/v1/orders/create/
{
  items: [{ product_id: 1, quantity: 2 }, ...],
  referral_code: "abc123xyz"  // optionnel
}
    ↓
Backend: create_order_atomic()
├─ Valider items (produits existent, quantités valides)
├─ Décrémenter stock (pour produits non-digitaux)
├─ Créer Commission (si referral_code valide)
└─ Retourner Order avec id, total, commission
    ↓
Frontend:
├─ cartStore.lastOrder = Order
├─ cartStore.clearCart()
├─ Afficher succès
└─ Redirection /checkout/success
```

### 5️⃣ Succès & Confirmations

```
Page /checkout/success
├─ Afficher: "Commande confirmée #123"
├─ Afficher: Total payé
├─ Afficher: Commission affilié (si applicable)
└─ Boutons:
   ├─ Voir mes commandes → /dashboard/orders
   └─ Accueil → /
```

---

## 🔐 Persistance & Session

### État du panier
- **Storage**: localStorage (clé: `agc-cart`)
- **Hydratation**: Zustand persist middleware
- **Durée**: Persistant jusqu'à clearCart()

### État utilisateur
```
État = localStorage (tokens) + Zustand store (user)

LOGIN flow:
1. POST /auth/login/ → { access, refresh }
2. localStorage['agc_access'] = access
3. localStorage['agc_refresh'] = refresh
4. authStore.user = getMe()
5. localStorage['agc-auth'] = { user }

REFRESH PAGE flow:
1. AuthInitializer.useAuthInitialize() appelé
2. Vérifier authService.isAuthenticated() → tokens en localStorage?
3. Si oui: fetchMe() → get /auth/me/ → restaurer user
4. Si erreur (401): logout et redirection /login

LOGOUT flow:
1. localStorage.removeItem('agc_access')
2. localStorage.removeItem('agc_refresh')
3. useAuthStore.setState({ user: null })
4. useCartStore.clearCart()
```

---

## 📡 API Endpoints

### Orders
- **POST** `/api/v1/orders/create/` — Créer commande (IsAuthenticated)
  ```json
  { "items": [{"product_id": 1, "quantity": 2}], "referral_code": "..." }
  ```
  Réponse: Order object

- **GET** `/api/v1/orders/` — Lister mes commandes (IsAuthenticated)
- **GET** `/api/v1/orders/{id}/` — Détail commande (IsAuthenticated)
- **GET** `/api/v1/orders/{id}/commission/` — Commission associée

### Auth
- **POST** `/api/v1/auth/login/` — Login
  ```json
  { "username": "...", "password": "..." }
  ```
  Réponse: `{ access, refresh }`

- **POST** `/api/v1/auth/register/` — Register
- **GET** `/api/v1/auth/me/` — User courant
- **POST** `/api/v1/auth/token/refresh/` — Refresh token

---

## ✅ Checklist de vérification

### Frontend Cart
- [ ] Bouton "Ajouter au panier" ajoute au store
- [ ] CartDrawer affiche les items
- [ ] Modifier quantité fonctionne
- [ ] Supprimer item fonctionne
- [ ] Clic "Passer commande" → /checkout
- [ ] Affiliation tracking code visible (si présent)

### Checkout
- [ ] Redirection /login si pas authentifié
- [ ] Redirection / si panier vide
- [ ] Récapitulatif items correct
- [ ] Total calculé correctement
- [ ] Info affiliation affichée

### Order Creation
- [ ] POST /orders/create/ réussit
- [ ] Order créée en DB
- [ ] Stock décrémenté (si non-digital)
- [ ] Commission créée (si referral_code)
- [ ] lastOrder affiché en succès

### Session Persistence
- [ ] Login → page refresh → utilisateur toujours connecté
- [ ] Panier persiste après refresh
- [ ] Logout → localStorage vidé
- [ ] Tokens expirés → auto-refresh ou logout

---

## 🐛 Debugging

### Logs Frontend
```javascript
// Dans Console du navigateur
console.log(JSON.stringify(useCartStore.getState(), null, 2))
console.log(JSON.stringify(useAuthStore.getState(), null, 2))

// Vérifier localStorage
console.log(localStorage.getItem('agc-cart'))
console.log(localStorage.getItem('agc-auth'))
console.log(localStorage.getItem('agc_access'))
```

### Logs Backend
```python
# Django logs
from django.conf import settings
import logging
logger = logging.getLogger('orders')
logger.info(f"Commande créée: {order.id}")

# tail logs
tail -f logs/django.log
```

### Problèmes courants

**Panier vide après reconnexion?**
- ✓ Vérifier localStorage['agc-cart'] contient les items
- ✓ Vérifier Zustand persist middleware fonctionne
- ✓ Vérifier useCartStore.getState() au chargement

**Erreur 401 après login?**
- ✓ Vérifier localStorage['agc_access'] existe
- ✓ Vérifier API client intercepteur injecte Bearer token
- ✓ Vérifier token n'est pas expiré

**Commission pas calculée?**
- ✓ Vérifier referral_code envoyé à /orders/create/
- ✓ Vérifier code valide en DB (Affiliation.tracking_code)
- ✓ Vérifier logique atomique en orders/services.py

---

## 📝 Notes importantes

1. **Transactions atomiques**: create_order_atomic() garantit que stock + commission sont créés ensemble ou rien
2. **Prix figés**: OrderItem.unit_price = prix au moment de la commande (intégrité comptable)
3. **Affiliation**: referral_code est optionnel, Commission créée seulement si code valide
4. **Session**: Utilise JWT tokens (access + refresh), pas sessions Django classiques
5. **Panier**: État client local, synchronisé au checkout seulement

---

## 🚀 Optimisations futures

- [ ] Coupon codes (10% discount, etc.)
- [ ] Stock en temps réel avec WebSocket
- [ ] Paiement Stripe intégré
- [ ] Emails de confirmation
- [ ] Historique panier abandonné
- [ ] Notifications de stock bas
- [ ] A/B testing variations checkout
