# 📊 Système de Panier & Session — Diagrammes d'architecture

Auteur : Gilles | Projet : AGC Space | Date : 19 avril 2026

---

## 🔄 Flux de restauration de session au démarrage

```
┌─────────────────────────────────────────────────────────────────┐
│ APP LOAD - Page Refresh ou Visite initiale                      │
└─────────────────────────────────────────────────────────────────┘
                            ↓
                      RootLayout.tsx
                            ↓
        ┌───────────────────────────────────────┐
        │ <Providers> (QueryClient)             │
        │   <AuthInitializer>  ← NEW!           │
        │     useAuthInitialize() hook           │
        │   </AuthInitializer>                  │
        │   {children}                           │
        │ </Providers>                           │
        └───────────────────────────────────────┘
                            ↓
          ┌─────────────────────────────────────┐
          │ useAuthInitialize() LOGIC           │
          └─────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────┐
        │ Check: user already in store?        │
        │   YES → Stop (already loaded)        │
        │   NO  → Continue                     │
        └──────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────┐
        │ Check: tokens in localStorage?       │
        │   localStorage['agc_access']         │
        │   YES → Continue                     │
        │   NO  → Stop (guest user)            │
        └──────────────────────────────────────┘
                            ↓
        ┌──────────────────────────────────────┐
        │ ASYNC: fetchMe()                     │
        │   GET /api/v1/auth/me/               │
        │   Header: Authorization: Bearer...   │
        └──────────────────────────────────────┘
                            ↓
                 ┌──────────┴──────────┐
                 ↓                     ↓
            SUCCESS 200           ERROR 401/500
            User data             (expired/invalid)
                 ↓                     ↓
        ┌────────────────┐   ┌────────────────┐
        │ set { user }   │   │ logout()       │
        │ Store updated  │   │ Clear tokens   │
        │ Pages render   │   │ user = null    │
        │ with user      │   │ Redirect /login│
        └────────────────┘   └────────────────┘
```

---

## 🛒 Flux complet panier + achat

```
┌─────────────────────────────────────────────────────────────────────┐
│ PAGE PRODUIT - Shop ou Dashboard                                    │
└─────────────────────────────────────────────────────────────────────┘
                            ↓
                  ┌─────────────────────┐
                  │ Afficher produits    │
                  │ avec BuyButtonBlock  │
                  └─────────────────────┘
                            ↓
            ┌───────────────────────────────────┐
            │ User clique "Acheter"             │
            │ (si stock > 0)                    │
            └───────────────────────────────────┘
                            ↓
            ┌───────────────────────────────────┐
            │ cartStore.addItem(product)        │
            │   → Si produit existe: +qty       │
            │   → Sinon: ajouter nouveau        │
            │   → localStorage['agc-cart'] mis   │
            └───────────────────────────────────┘
                            ↓
            ┌───────────────────────────────────┐
            │ Event: agc:open-cart              │
            │ CartDrawer s'ouvre               │
            └───────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│ CART DRAWER - Viewing items                                          │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Mon panier (3)                                                  │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ [Item 1] Formation Django                 97€   [−] 1 [+]      │ │
│ │ [Item 2] Masterclass Web                  197€  [−] 2 [+]      │ │
│ │ [Item 3] Coaching 1-on-1                  1497€ [−] 1 [+] [✕] │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ Total: 2788€                                                    │ │
│ │ [PASSER LA COMMANDE] → /checkout                               │ │
│ └─────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│ User can:                                                            │
│  • Modify quantities                                                 │
│  • Remove items                                                      │
│  • Continue shopping                                                 │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
            ┌───────────────────────────────────┐
            │ Click "Passer la commande"        │
            │ Navigation to /checkout           │
            └───────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│ CHECKOUT PAGE - Recap & Payment                                      │
│                                                                      │
│ Checks:                                                              │
│  ✓ Is authenticated? NO → Redirect /login                           │
│  ✓ Cart not empty?    YES → Continue                                │
│  ✓ User data exists?  YES → Continue                                │
│                                                                      │
│ Display:                                                             │
│  • All items with prices                                            │
│  • Subtotal for each                                                │
│  • TOTAL                                                            │
│  • Affiliation info (if tracking code)                              │
│  • Payment buttons: [Stripe] [Confirmer]                            │
└──────────────────────────────────────────────────────────────────────┘
                            ↓
                ┌───────────┴──────────┐
                ↓                      ↓
            Stripe Pay         Direct Pay
                ↓                      ↓
        Redirect Stripe          ┌──────────────┐
        Session URL              │ POST /orders/│
                ↓                │  create/     │
                                 └──────────────┘
                                        ↓
            ┌─────────────────────────────────────────────┐
            │ Backend: create_order_atomic()              │
            │                                             │
            │  1. Validate items exist + prices         │
            │  2. Decrement stock (non-digital)          │
            │  3. Create OrderItems                      │
            │  4. Create Commission (if referral_code)   │
            │  5. Return Order object                    │
            │     (Transaction: all or nothing)          │
            └─────────────────────────────────────────────┘
                            ↓
            ┌─────────────────────────────────┐
            │ Frontend: Handle Response       │
            │                                 │
            │ Success 201:                    │
            │  • cartStore.lastOrder = Order  │
            │  • cartStore.clearCart()        │
            │  • setStep('success')           │
            │  • localStorage cleared         │
            │                                 │
            │ Error 400/401/500:              │
            │  • Display error message        │
            │  • Keep items in cart           │
            │  • Allow retry                  │
            └─────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────────┐
│ SUCCESS PAGE - Order Confirmation                                    │
│                                                                      │
│ ┌────────────────────────────────────────────────────────────────┐  │
│ │                                                            🎉   │  │
│ │                    Commande confirmée !                       │  │
│ │                    Commande #12345                           │  │
│ │                    Total: 2788€                              │  │
│ │                                                              │  │
│ │  ┌──────────────────────────────────────────────────────┐   │  │
│ │  │ 💚 Commission affilié générée                        │   │  │
│ │  │   Montant: 27.88€ (1%)                              │   │  │
│ │  └──────────────────────────────────────────────────────┘   │  │
│ │                                                              │  │
│ │ [MES COMMANDES] [ACCUEIL]                                   │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                      │
│ Post-order:                                                          │
│  • User still authenticated                                          │
│  • Session persisted                                                 │
│  • Can view order in /dashboard/orders                               │
│  • Can continue shopping                                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 💾 État & Persistance

```
┌────────────────────────────────────────────────────────────────┐
│ FRONTEND STATE MANAGEMENT                                      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  useAuthStore (Zustand + persist)                             │
│  ├─ State:                                                    │
│  │  ├─ user: User | null                                     │
│  │  ├─ isLoading: boolean                                    │
│  │  └─ error: string | null                                 │
│  │                                                            │
│  ├─ Actions:                                                 │
│  │  ├─ login(username, password)                            │
│  │  ├─ register(payload)                                    │
│  │  ├─ fetchMe()  ← restaure user depuis backend            │
│  │  ├─ logout()   ← vide tokens                             │
│  │  └─ hasRole(role)                                        │
│  │                                                            │
│  └─ Persist:                                                 │
│     localStorage['agc-auth'] = { user: {...} }              │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  useCartStore (Zustand + persist)                             │
│  ├─ State:                                                    │
│  │  ├─ items: CartItem[]                                    │
│  │  ├─ isOpen: boolean                                      │
│  │  ├─ isCheckingOut: boolean                               │
│  │  ├─ lastOrder: Order | null                              │
│  │  └─ error: string | null                                 │
│  │                                                            │
│  ├─ Actions:                                                 │
│  │  ├─ addItem(product, qty)                                │
│  │  ├─ removeItem(productId)                                │
│  │  ├─ updateQuantity(productId, qty)                       │
│  │  ├─ clearCart()                                          │
│  │  ├─ checkout(referralCode?)                              │
│  │  └─ openCart() / closeCart()                             │
│  │                                                            │
│  └─ Persist:                                                 │
│     localStorage['agc-cart'] = { items: [...] }             │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  authService (JWT Tokens)                                     │
│  ├─ Login:                                                   │
│  │  └─ POST /auth/login/ → { access, refresh }             │
│  │                                                            │
│  ├─ Store:                                                   │
│  │  ├─ localStorage['agc_access'] = token (short-lived)     │
│  │  └─ localStorage['agc_refresh'] = token (long-lived)     │
│  │                                                            │
│  ├─ Usage:                                                   │
│  │  └─ All requests: Header Authorization: Bearer {access}  │
│  │                                                            │
│  ├─ Auto-refresh:                                            │
│  │  └─ On 401: Use refresh token → get new access token    │
│  │                                                            │
│  └─ Logout:                                                  │
│     └─ Clear both tokens from localStorage                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘

Timeline:
─────────────────────────────────────────────────────────────────

00:00 - Page Load
│
├─→ AuthInitializer mounts
│   └─→ useAuthInitialize() hook
│       └─→ Check tokens in localStorage
│           └─→ fetchMe() if tokens exist
│               └─→ Restore user to store
│
├─→ CartDrawer loads
│   └─→ Zustand persist hydrates from localStorage['agc-cart']
│
└─→ Pages render with restored state

PERSISTENCE LAYERS:
──────────────────
localStorage          Zustand persist         Memory (JS)
├─ agc_access         ├─ agc-auth:            ├─ authStore
├─ agc_refresh        │  └─ { user }          ├─ cartStore
├─ agc-auth           │                       └─ temp state
├─ agc-cart           ├─ agc-cart:
│                     │  └─ { items }
└─ (other)            │
                      └─ (auto-saved)

Order of precedence for auth:
  1. Memory (JS) → Fastest
  2. localStorage → Restore on load
  3. Backend (/auth/me/) → Source of truth
```

---

## 🔐 JWT Token Flow

```
LOGIN:
User enters credentials
        ↓
POST /auth/login/
{ username: "user", password: "pass" }
        ↓
Backend validates & creates tokens
{ access: "eyJ...", refresh: "eyJ..." }
        ↓
Frontend stores:
  localStorage['agc_access'] = access      (expires: 5 minutes)
  localStorage['agc_refresh'] = refresh    (expires: 7 days)
        ↓
axios interceptor:
  All requests get header: Authorization: Bearer {access}

REFRESH (Auto):
After 5 minutes, token expires
        ↓
API call gets 401 Unauthorized
        ↓
Interceptor catches 401
        ↓
POST /auth/token/refresh/
{ refresh: "eyJ..." }
        ↓
Backend validates & creates NEW access token
{ access: "eyJ..." }
        ↓
localStorage['agc_access'] = new access
        ↓
Retry original request with NEW token ✓

LOGOUT:
User clicks "Déconnexion"
        ↓
authService.logout():
  localStorage.removeItem('agc_access')
  localStorage.removeItem('agc_refresh')
  localStorage.removeItem('agc-auth')
        ↓
useAuthStore.setState({ user: null })
        ↓
useCartStore.setState({ items: [] })
        ↓
Redirect /login
```

---

## 📈 State Diagram

```
                    ┌──────────────────┐
                    │  Initial State   │
                    │  user: null      │
                    │  items: []       │
                    └────────┬─────────┘
                             │
                    ┌────────▼────────┐
                    │ Login Page      │
                    │ /login          │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ POST /auth/...  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ AUTHENTICATED   │
                    │ user: { ... }   │
                    │ Can checkout    │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                                 │
      ┌─────▼─────┐                    ┌─────▼─────┐
      │Add to cart│                    │  Checkout │
      │items: [1] │                    │ /checkout │
      └─────┬─────┘                    └─────┬─────┘
            │                                │
      ┌─────▼──────────┐          ┌──────────▼────────┐
      │items: [1, 2]   │          │ POST /orders/...  │
      │isOpen: true    │          │ Create order      │
      └─────┬──────────┘          └──────────┬────────┘
            │                                │
      ┌─────▼──────────┐          ┌──────────▼────────────┐
      │Continue adding │          │ lastOrder: { id: 1 } │
      │or checkout     │          │ items: [] (cleared)   │
      └────────────────┘          └──────────┬───────────┘
                                             │
                                    ┌────────▼──────────┐
                                    │SUCCESS PAGE       │
                                    │/checkout/success  │
                                    └────────┬──────────┘
                                             │
                                    ┌────────▼──────────┐
                                    │Logout option      │
                                    │or continue shop   │
                                    └────────┬──────────┘
                                             │
                                    ┌────────▼──────────┐
                                    │ Initial State     │
                                    │(if logout)        │
                                    └───────────────────┘
```

---

Generated: 19 avril 2026 | Author: Gilles | Project: AGC Space
