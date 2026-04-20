# 🧪 Guide de test — Système de panier, achat et persistance de session

Auteur : Gilles | Projet : AGC Space | Date : 19 avril 2026

## ✅ Prérequis

- Backend Django running: `python manage.py runserver`
- Frontend Next.js running: `npm run dev`
- Navigateur: Ouvrir DevTools (F12)
- Test user: créé via register ou fixtures

---

## 📝 Checklist: Test complet du flux

### 1. Test Initial — Vérifier les stores vides

**Actions:**
1. Ouvrir http://localhost:3000
2. Ouvrir DevTools → Console

**Vérifications:**
```javascript
// Dans la console:
console.log(JSON.stringify(useCartStore.getState(), null, 2))
console.log(JSON.stringify(useAuthStore.getState(), null, 2))
```

**Attendu:**
```json
Cart: { items: [], isOpen: false, isCheckingOut: false, lastOrder: null, error: null }
Auth: { user: null, isLoading: false, error: null }
```

---

### 2. Test Session Persistence — Persistance après connexion

**Étape 1: Login**
1. Cliquer sur "Connexion" → `/login`
2. Entrer credentials: `username: testuser`, `password: password123`
3. Cliquer "Se connecter"

**Attendre:** Redirection vers `/dashboard` ou `/`

**Vérifications après login:**
```javascript
// Console
useAuthStore.getState().user
localStorage.getItem('agc_access')
localStorage.getItem('agc-auth')
```

**Attendu:**
```
✓ user: { id: 1, username: 'testuser', email: '...', roles: [...] }
✓ agc_access: '<long_jwt_token>'
✓ agc-auth: '{"user":{...}}'
```

**Étape 2: Refresh page (F5)**
1. La page se rafraîchit
2. Attendre le chargement complet

**Vérifications après refresh:**
```javascript
useAuthStore.getState().user?.username  // Doit être 'testuser'
```

**Attendu:**
```
✓ Username restant: 'testuser'
✓ Pas de redirection vers /login
✓ Barre de navigation affiche l'utilisateur connecté
```

**Si ÉCHOUE:** 
- Vérifier localStorage n'est pas vide
- Vérifier authService.isAuthenticated() retourne true
- Vérifier les erreurs console pour 401 errors

---

### 3. Test Panier — Ajouter et gérer des produits

**Étape 1: Naviguer vers une page avec BuyButtonBlock**
1. Cliquer sur un produit dans le catalogue
2. Ou aller sur `/shop`

**Étape 2: Ajouter au panier**
1. Cliquer sur "Acheter maintenant" (ou bouton similaire)
2. Drawer du panier doit s'ouvrir

**Vérifications:**
```javascript
// Console
useCartStore.getState().items
useCartStore.getState().isOpen
```

**Attendu:**
```
✓ items: [{ product: {...}, quantity: 1 }]
✓ isOpen: true
```

**Étape 3: Modifier le panier**
1. Augmenter la quantité (bouton +)
2. Vérifier le total se met à jour
3. Ajouter un autre produit
4. Vérifier le nombre d'items

**Vérifications:**
```javascript
useCartStore.getState().totalItems()   // Doit augmenter
useCartStore.getState().totalPrice()   // Doit augmenter
```

**Attendu:**
```
✓ totalItems: 2 (ou plus)
✓ totalPrice: Montant correct
```

---

### 4. Test Persistance Panier — Panier survit après refresh

**Étape 1: Ajouter des produits (voir section 3)**
1. Ajouter 2-3 produits au panier
2. Noter le total

**Étape 2: Refresh page (F5)**
1. La page se rafraîchit

**Vérifications:**
```javascript
// Console après refresh
useCartStore.getState().items.length
useCartStore.getState().totalPrice()
```

**Attendu:**
```
✓ items encore dans le panier
✓ totalPrice = même valeur qu'avant refresh
✓ localStorage['agc-cart'] contient les items
```

**Si ÉCHOUE:**
- Vérifier `persist` middleware dans cartStore
- Vérifier localStorage n'est pas en mode private/incognito
- Vérifier `partialize` fonction correcte

---

### 5. Test Affiliation — Tracking code avec panier

**Prérequis:** Avoir un code de tracking affilié

**Étape 1: Simuler un lien affilié**
1. Ajouter dans l'URL: `?ref=AFFILIATE_CODE`
2. Ou cliquer un lien avec code de tracking
3. Vérifier le cookie: `agc_ref=AFFILIATE_CODE`

**Vérifications:**
```javascript
// Console
document.cookie
// Ou
useAffiliationStore.getState().trackingCode
```

**Attendu:**
```
✓ trackingCode visible dans le store
✓ Bouton "Acheter" affiche "Affiliation activée"
```

**Étape 2: Aller au checkout avec affiliation**
1. Ajouter un produit
2. Cliquer "Passer la commande"
3. Vérifier que le code s'affiche

**Attendu:**
```
✓ Page checkout affiche: "✓ Achat via lien affilié — commission calculée automatiquement"
```

---

### 6. Test Checkout — Flux complet de commande

**Étape 1: Naviguer vers checkout**
1. Panier avec items (voir section 3)
2. Cliquer "Passer la commande"
3. Redirection vers `/checkout`

**Vérifications:**
```javascript
// Console
useAuthStore.getState().user // Doit être connecté
useCartStore.getState().items // Doit avoir items
```

**Attendu:**
```
✓ Page affiche le récapitulatif
✓ Chaque item affiché avec quantité et prix
✓ Total correct
```

**Étape 2: Valider la commande**
1. Cliquer "Confirmer la commande"
2. Attendre le traitement

**Network Tab (F12 → Network):**
```
POST /api/v1/orders/create/ → 201 Created
```

**Réponse attendue:**
```json
{
  "id": 123,
  "customer": 1,
  "referral_code": "...",
  "status": "pending",
  "total": "97.00",
  "items": [{"product_id": 1, "quantity": 1, ...}],
  "commission": null ou {...},
  "created_at": "2026-04-19T..."
}
```

**Étape 3: Vérifier le succès**
1. Redirection vers `/checkout/success`
2. Affichage "Commande confirmée !"

**Vérifications:**
```javascript
// Console
useCartStore.getState().lastOrder  // Doit avoir l'ordre créée
useCartStore.getState().items      // Doit être vide
```

**Attendu:**
```
✓ lastOrder.id: 123
✓ items: []
✓ Affiche numéro commande
✓ Affiche total payé
✓ Commission visible (si applicable)
```

---

### 7. Test Session After Checkout — Session persiste après achat

**Étape 1: Après commande confirmée**
1. Cliquer "Mes commandes"
2. Redirection vers `/dashboard/orders`

**Vérifications:**
```javascript
// Console
useAuthStore.getState().user?.username  // Doit rester connecté
```

**Étape 2: Vérifier la commande dans l'historique**
1. Page affiche la liste des commandes
2. La commande juste créée doit y être

**Network Tab:**
```
GET /api/v1/orders/ → 200 OK
```

---

### 8. Test Logout & Session Cleanup

**Étape 1: Cliquer "Déconnexion"**
1. Localiser le bouton de logout (généralement dans header/menu)
2. Cliquer dessus

**Vérifications immédiatement après:**
```javascript
// Console
useAuthStore.getState().user           // Doit être null
useCartStore.getState().items          // Doit être vide
localStorage.getItem('agc_access')     // Doit être null
localStorage.getItem('agc-auth')       // Doit être null (ou {})
```

**Attendu:**
```
✓ Redirection vers /login ou /
✓ Tous les tokens supprimés
✓ Panier vidé
✓ user = null
```

**Étape 2: Refresh après logout**
1. Appuyer F5

**Attendu:**
```
✓ Toujours non authentifié
✓ Panier vide
```

---

### 9. Test Erreurs — Vérifier la gestion

**Erreur 9.1: Ajouter un produit stock 0**
1. Trouver un produit avec stock = 0
2. Cliquer "Acheter" (bouton doit être disabled)

**Attendu:**
```
✓ Bouton disabled
✓ Texte "Rupture de stock"
✓ Pas d'ajout au panier
```

**Erreur 9.2: Checkout sans connexion**
1. Logout (voir section 8)
2. Aller à `/checkout`

**Attendu:**
```
✓ Redirection vers /login
✓ Message "Connexion requise"
```

**Erreur 9.3: Tokens expirés**
1. Supprimer agc_access du localStorage
2. Faire une action qui nécessite auth

**Attendu:**
```
✓ Auto-refresh du token via intercepteur
✓ Ou redirection /login si refresh échoue
```

---

## 🐛 Debugging avancé

### Activer verbose logging

```javascript
// Dans les stores
localStorage.setItem('DEBUG', 'agc:*')
```

### Vérifier localStorage complet

```javascript
for (let i = 0; i < localStorage.length; i++) {
  const key = localStorage.key(i)
  console.log(key + ':', localStorage.getItem(key))
}
```

### Vérifier Network requests

F12 → Network → Filter par `api`
```
POST /api/v1/auth/login/
POST /api/v1/orders/create/
GET /api/v1/auth/me/
GET /api/v1/orders/
```

### Backend logs

```bash
# Terminal 1: Backend
python manage.py runserver

# Regarder les logs (tail -f logs/django.log)
tail -f logs/django.log | grep -E "Order|Auth|Affiliation"
```

### Console logs frontend

```javascript
// Activer debug mode
localStorage.setItem('DEBUG_AUTH', 'true')
localStorage.setItem('DEBUG_CART', 'true')

// Dans app/auth-initializer.tsx ou Providers, ajouter:
if (localStorage.getItem('DEBUG_AUTH')) {
  console.log('[Auth Debug]', useAuthStore.getState())
}
```

---

## 📊 Résumé des cas de test

| # | Cas | Statut | Notes |
|---|-----|--------|-------|
| 1 | Stores vides initiaux | ✓ | Baseline |
| 2 | Session persiste après login | ✓ | Clé: authService.isAuthenticated() |
| 3 | Session survit refresh | ✓ | Clé: localStorage + Zustand persist |
| 4 | Ajouter produit au panier | ✓ | Clé: useCartStore.addItem() |
| 5 | Panier persiste après refresh | ✓ | Clé: localStorage['agc-cart'] |
| 6 | Panier avec affiliation | ✓ | Clé: referral_code envoyé au checkout |
| 7 | Checkout crée commande | ✓ | Clé: POST /orders/create/ |
| 8 | Session après achat | ✓ | Clé: user reste connecté |
| 9 | Logout vide tout | ✓ | Clé: localStorage cleared |
| 10 | Gestion erreurs (stock, 401, etc) | ✓ | Robustesse |

---

## 🎯 Succès = ✅ Tous les cas passent

Si tous les tests passent: **Système opérationnel ✅**
