# Textly.ai – Starter (Flask)

Ein minimal lauffähiges Grundgerüst für dein Textly.ai SaaS:
- Registrierung & Login (E-Mail/Passwort)
- Platzhalter für OAuth (Apple/Google/Facebook/X)
- Freemium-Quota (3 Texte/Tag)
- Pricing-Seite mit Week/Month/Year/Lifetime
- Payhip-Webhook (`/webhooks/payhip`) – setzt Abo auf aktiv
- Simple UI im „Smart & Playful“-Stil

## Lokal starten

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_SECRET_KEY=change-this
python app.py
```

Öffne: http://localhost:5000

## Deploy (Render)
1. Repo zu GitHub pushen.
2. Render -> New Web Service -> Build & Deploy.
3. Umgebungsvariablen setzen:
   - FLASK_SECRET_KEY
   - PAYHIP_WEBHOOK_SECRET
4. Start Command (Render erkennt Procfile automatisch; sonst):
   ```
   gunicorn -w 2 -k gthread -t 120 -b 0.0.0.0:$PORT app:app
   ```

## Payhip einrichten
- Vier Produkte: `weekly`, `monthly`, `yearly`, `lifetime` (als Handle).
- Webhook-URL: `https://<deine-domain>/webhooks/payhip`
- Webhook Secret im Payhip-Dashboard setzen und als `PAYHIP_WEBHOOK_SECRET` in Render hinterlegen.

## OAuth (als nächster Schritt)
- Routen `/auth/google`, `/auth/apple`, `/auth/facebook`, `/auth/x` im Backend mit Authlib ergänzen.
- In den Provider-Konsolen Redirect-URLs eintragen: `https://<deine-domain>/auth/<provider>/callback`

## Wichtige Hinweise
- Dies ist ein Starter. Die eigentliche Textgenerierung ist ein **Platzhalter** (`/api/generate`). 
- Für echte Mails SMTP/SendGrid/Postmark konfigurieren.
- Für Produktion: Passwort-Hashing mit bcrypt (bereit), Rate Limiting & CSRF ergänzen.
