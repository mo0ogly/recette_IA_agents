# Runbook -- exposer la console sur le LAN (acces depuis un autre poste)

Par defaut la console (vite) ecoute en boucle locale (`127.0.0.1:5174`) : elle
n'est joignable QUE depuis ce poste, quel que soit l'etat du firewall (le
socket n'ecoute pas sur l'interface LAN). C'est voulu (surface reduite). Pour
un acces distant, il faut trois choses alignees -- pas seulement ouvrir le
port.

## Ce qu'il faut (trois pieces)

1. **vite ecoute sur toutes les interfaces** (`--host 0.0.0.0`).
2. **L'URL de l'API cablee dans la console pointe sur l'IP LAN de CE poste**
   (`http://<LAN_IP>:8090`), sinon le navigateur distant appelle sa PROPRE
   boucle locale.
3. **L'API autorise l'origine LAN de la console dans CORS**, sinon le
   navigateur bloque les reponses cross-origin.

## Procedure

Mode LAN opt-in cable dans `recette.sh` / `cicd/platform.sh` (R19 : jamais de
lancement vite a la main). L'IP LAN est auto-detectee (`lan_ip`, source de la
route par defaut).

1. Remonter l'API Docker en autorisant l'origine LAN (R27, l'API tourne en
   Docker). Remplacer `<LAN_IP>` par l'IP de ce poste (`hostname -I`) :

   ```
   export INSPECT_IA_AGENTS_CORS_ORIGINS="http://<LAN_IP>:5174,http://localhost:5174,http://127.0.0.1:5174,http://localhost:5173,http://127.0.0.1:5173"
   docker compose up -d api
   ```

   Prerequis : la ligne `INSPECT_IA_AGENTS_CORS_ORIGINS` du service `api` dans
   `docker-compose.yml` doit etre interpolable
   (`"${INSPECT_IA_AGENTS_CORS_ORIGINS:-<defauts loopback>}"`). Sans ca la
   valeur codee en dur ignore l'export.

2. Demarrer la console en mode LAN :

   ```
   INSPECT_IA_AGENTS_CONSOLE_LAN=1 ./recette.sh console start
   ```

   Le lanceur bind vite sur `0.0.0.0`, cable `VITE_INSPECT_IA_AGENTS_API_URL`
   sur `http://<LAN_IP>:8090`, et affiche l'URL joignable
   (`http://<LAN_IP>:5174`).

3. Depuis le poste distant, ouvrir `http://<LAN_IP>:5174` (l'IP de CE poste,
   verifiee par `hostname -I` -- ne pas confondre avec une autre machine).

## Verification

```
ss -tlnp | grep :5174                       # doit montrer 0.0.0.0:5174 (pas 127.0.0.1)
curl -o /dev/null -w '%{http_code}\n' http://<LAN_IP>:5174/       # 200
curl -D - -o /dev/null http://<LAN_IP>:8090/assist/topics -H "Origin: http://<LAN_IP>:5174" | grep -i access-control-allow-origin
```

Le dernier doit renvoyer `access-control-allow-origin: http://<LAN_IP>:5174`.

## Revenir en local seul

`./recette.sh console stop` puis `./recette.sh console start` (sans la var)
rebind sur `127.0.0.1`. Remonter l'API sans l'export CORS revient aux origines
loopback par defaut.

## Securite

L'exposition LAN ouvre la console ET l'API a tout le sous-reseau. A reserver a
un reseau de confiance (lab interne). L'API n'a pas d'auth activee en dev
(`INSPECT_IA_AGENTS_JWT_SIGNING_KEY` non pose) : ne pas exposer hors d'un LAN
maitrise.
