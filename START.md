# AGC Space — Lancer le projet en tunnel Ngrok

> Un seul port, un seul tunnel, frontend + backend fusionnés.
> Architecture : `Ngrok → :8000 (Django) → proxy interne → :3000 (Next.js)`

---

## Prérequis vérifiés

| Outil | Version détectée |
|-------|-----------------|
| Python / Django | 5.2.3 |
| Node.js / Next.js | 14.2.5 |
| httpx (proxy) | 0.28.1 ✅ |
| gunicorn | 25.3.0 ✅ |
| ngrok | 3.36.1 ✅ |

---

## Étape 1 — Ouvrir 3 terminaux

Tu as besoin de **3 terminaux** ouverts dans le dossier `EcomMVP/`.

---

## Terminal 1 — Lancer Next.js (frontend interne)

```powershell
cd frontend
npm run dev
```

> Next.js démarre sur `http://localhost:3000`.
> Ce port n'est **jamais** exposé directement — Django le proxifie.

Attends de voir :
```
✓ Ready in Xs
○ Local: http://localhost:3000
```

---

## Terminal 2 — Lancer Django (backend + proxy)

```powershell
python manage.py runserver 8000
```

> Django démarre sur `http://localhost:8000`.
> Toute requête non-API est automatiquement transmise à Next.js.

Vérifie que le proxy fonctionne en ouvrant `http://localhost:8000` dans ton navigateur — tu dois voir l'app React.

---

## Terminal 3 — Ouvrir le tunnel Ngrok

```powershell
ngrok http 8000
```

Ngrok affiche une URL publique du type :
```
Forwarding  https://xxxx-xx-xx-xxx-xx.ngrok-free.app -> http://localhost:8000
```

**C'est cette URL HTTPS que tu partages.**

---

## Étape 2 — Mettre à jour les variables d'environnement avec l'URL Ngrok

À chaque nouveau tunnel, l'URL Ngrok change. Tu dois mettre à jour **2 fichiers** :

### `.env` (backend Django)

```env
ALLOWED_HOSTS=localhost,127.0.0.1,xxxx-xx-xx-xxx-xx.ngrok-free.app
CORS_ALLOWED_ORIGINS=http://localhost:3000,https://xxxx-xx-xx-xxx-xx.ngrok-free.app
```

### `frontend/.env.local` (frontend Next.js)

```env
NEXT_PUBLIC_API_URL=https://xxxx-xx-xx-xxx-xx.ngrok-free.app
```

> Remplace `xxxx-xx-xx-xxx-xx.ngrok-free.app` par ton URL réelle.

Après modification, **redémarre les deux serveurs** (Ctrl+C dans Terminal 1 et 2, puis relancer).

---

## Récapitulatif des URLs

| Accès | URL |
|-------|-----|
| App locale | `http://localhost:8000` |
| App publique (tunnel) | `https://xxxx.ngrok-free.app` |
| API Django | `https://xxxx.ngrok-free.app/api/v1/` |
| Admin Django | `https://xxxx.ngrok-free.app/admin/` |
| Health check | `https://xxxx.ngrok-free.app/health/` |
| Next.js (interne) | `http://localhost:3000` — ne pas partager |

---

## Dépannage

### Page blanche ou "Next.js n'est pas démarré"
→ Next.js (Terminal 1) n'est pas encore prêt. Attends quelques secondes et recharge.

### Erreur 401 / token invalide après changement d'URL
→ L'URL de l'API a changé. Vide le localStorage du navigateur (`F12 → Application → Local Storage → Clear`) et reconnecte-toi.

### Ngrok affiche "ERR_NGROK_3200" (tunnel expiré)
→ Relance `ngrok http 8000` et mets à jour les `.env` avec la nouvelle URL.

### Django refuse la connexion (`DisallowedHost`)
→ L'URL Ngrok n'est pas dans `ALLOWED_HOSTS`. Ajoute-la dans `.env` et redémarre Django.

### CORS bloqué dans la console navigateur
→ L'URL Ngrok n'est pas dans `CORS_ALLOWED_ORIGINS`. Ajoute-la dans `.env` et redémarre Django.

---

## Commande rapide (si `make` est installé)

```powershell
# Lance Next.js + Django en une commande (Terminal 1)
make tunnel

# Dans un autre terminal (Terminal 2)
ngrok http 8000
```

---

## Ordre de démarrage résumé

```
1. npm run dev          (frontend, Terminal 1)
2. python manage.py runserver 8000   (backend, Terminal 2)
3. ngrok http 8000      (tunnel, Terminal 3)
4. Mettre à jour .env et frontend/.env.local avec l'URL Ngrok
5. Redémarrer Terminal 1 et 2
```
