# automatic-youtube-downloader

Chaque jour, ce script regarde une ou plusieurs playlists YouTube, télécharge en **MP3 320 kbps** les morceaux
qu'il n'a pas encore récupérés et les dépose dans un dossier de ton **Google Drive**.

- Fichiers nommés `Artiste - Titre.mp3`, sans les mentions du type « (Official Video) », mais en gardant
  « (Extended Mix) », « (X Remix) », etc.
- Tags ID3 (artiste, titre) et pochette carrée, lisibles par Rekordbox, Serato et Traktor.
- Au premier lancement, il récupère toute la playlist. Ensuite, seulement les nouveautés.
- Il tourne tout seul sur Google Cloud. Ton ordinateur n'a pas besoin d'être allumé.

> Usage personnel uniquement. Télécharger depuis YouTube n'est pas autorisé par ses conditions d'utilisation :
> à toi de voir ce que tu fais des fichiers, et soutiens les artistes (Bandcamp, Beatport…).

## Combien ça coûte ?

**0 € en pratique** : tout reste dans le niveau gratuit de Google Cloud (un lancement par jour, quelques minutes).
Google demande quand même une carte bancaire pour activer le projet. Mets une alerte de budget à 1 € (étape 1)
et tu seras prévenu au moindre centime.

Seule limite : ton Google Drive gratuit fait 15 Go, soit environ 1 000 morceaux.

## Comment ça marche

```
Cloud Scheduler (tous les jours)
        │
        ▼
Cloud Run Job ── lit les playlists ──► YouTube
        │        télécharge + convertit en MP3
        │
        ├── mémorise les morceaux déjà faits ──► Cloud Storage (state.json)
        └── dépose les MP3 ───────────────────► Google Drive
```

---

## Installation (environ 30 min, une seule fois)

### Ce qu'il te faut

- Un compte Google (Gmail suffit) et une carte bancaire.
- **Python 3.10+**, pour l'étape 4 uniquement.
- **Google Cloud CLI** (`gcloud`) : https://cloud.google.com/sdk/docs/install
- Un terminal **bash** : Terminal sur Mac/Linux, **Git Bash** sur Windows.

> Pas envie d'installer gcloud ? Tu peux faire les étapes 5 et 6 dans
> [Cloud Shell](https://shell.cloud.google.com), un terminal dans le navigateur où tout est déjà installé.
> Il suffit d'y envoyer le dossier du projet avec ton `config.env` et ton `token.json`.

### 1. Créer le projet Google Cloud

1. Va sur https://console.cloud.google.com/projectcreate et crée un projet, par exemple `dj-downloader`.
   Note son **ID** (affiché sous le nom, par exemple `dj-downloader-123456`).
2. Lie un compte de facturation : https://console.cloud.google.com/billing/linkedaccount
3. *(Recommandé)* Crée une alerte de budget à 1 € : menu **Facturation → Budgets et alertes → Créer un budget**.
4. Dans ton terminal :
   ```bash
   gcloud auth login
   gcloud config set project TON_PROJECT_ID
   gcloud services enable drive.googleapis.com
   ```

### 2. Récupérer le code et le configurer

```bash
git clone https://github.com/PaulVial/automatic-youtube-downloader.git
cd automatic-youtube-downloader
cp config.example.env config.env
```

Ouvre `config.env` et remplis au minimum :

```
PROJECT_ID=dj-downloader-123456
PLAYLISTS=https://www.youtube.com/playlist?list=PLxxxx,https://www.youtube.com/playlist?list=PLyyyy
```

Les playlists doivent être **publiques** ou **non répertoriées**. Les autres options (nom du dossier Drive, heure
du lancement…) sont expliquées dans le fichier.

### 3. Autoriser l'accès à Google Drive

Le script a besoin de ta permission pour déposer des fichiers dans ton Drive. On crée pour ça une « app OAuth »
privée, qui ne sert qu'à toi.

Dans la console, ouvre **Google Auth Platform** : https://console.cloud.google.com/auth/overview

1. **Commencer** : nom de l'app `automatic-youtube-downloader`, ton adresse e-mail. Type d'audience : **Externe**.
2. **Branding** : Google exige ces champs pour passer en Production. Comme l'app n'utilise qu'une permission
   « non sensible », il ne relit pas les pages : il faut juste qu'elles existent.

   | Champ | Valeur |
   |---|---|
   | Page d'accueil de l'application | `https://github.com/PaulVial/automatic-youtube-downloader` |
   | Règles de confidentialité | `https://github.com/PaulVial/automatic-youtube-downloader/blob/main/PRIVACY.md` |
   | Domaines autorisés | `github.com` |
   | Adresse e-mail d'assistance / du développeur | ton adresse e-mail |

   Le repo GitHub doit être **public** pour que ces liens marchent. Si tu ne veux pas publier le code, colle le
   contenu de [PRIVACY.md](PRIVACY.md) dans un [Gist public](https://gist.github.com) et utilise l'URL du Gist
   pour les deux champs.
3. **Audience** : clique sur **Publier l'application** pour la passer en **Production**.
   ⚠️ Étape indispensable : en mode « Test », l'autorisation expire au bout de 7 jours et le script s'arrête.
4. **Clients → Créer un client** : type **Application de bureau** (Desktop app), puis **Télécharger le JSON**.
   Renomme le fichier en `client_secret.json` et place-le dans le dossier du projet.

### 4. Générer le token Drive

```bash
pip install google-auth-oauthlib
python scripts/get_drive_token.py client_secret.json
```

Un navigateur s'ouvre : connecte-toi avec le compte Google **dont tu veux utiliser le Drive**. Si Google affiche
« Application non validée », clique sur **Paramètres avancés → Accéder à automatic-youtube-downloader**. C'est normal, c'est
ta propre app.

Le script crée `token.json`. **Ce fichier donne accès à ton Drive : ne le partage pas.**

> L'app ne voit que les fichiers qu'elle a créés elle-même (permission `drive.file`) : elle n'a pas accès au reste
> de ton Drive. C'est aussi pour ça que le dossier de destination est créé par le script, et qu'il ne peut pas
> utiliser un dossier qui existe déjà.

### 5. *(Optionnel)* Tester sur ton ordinateur

Nécessite Docker. Voir ce qui serait téléchargé, sans rien télécharger :

```bash
docker build -t automatic-youtube-downloader .
docker run --rm --env-file config.env automatic-youtube-downloader --dry-run
```

Télécharger 1 morceau pour de vrai dans ton Drive :

```bash
# Sous Git Bash (Windows), ajoute MSYS_NO_PATHCONV=1 devant la commande.
docker run --rm --env-file config.env \
  -e STATE_URI=/data/state.json -e DRIVE_TOKEN_FILE=/data/token.json \
  -v "$(pwd):/data" automatic-youtube-downloader --limit 1
```

Pas de doublon à craindre plus tard : avant de télécharger un morceau, le script vérifie s'il est déjà dans le
Drive.

### 6. Déployer sur Google Cloud

```bash
bash deploy/deploy.sh
```

Compte environ 5 minutes. Le script crée tout ce qu'il faut et peut être relancé sans risque.

Lance ensuite un premier run tout de suite, sans attendre demain 6h :

```bash
gcloud run jobs execute automatic-youtube-downloader --region=europe-west1
```

Le premier run récupère toute la playlist : compte environ 20 secondes par morceau. Le dossier
**DJ - YouTube** apparaît dans ton Drive.

---

## Au quotidien

| Je veux… | Je fais… |
|---|---|
| Ajouter ou retirer une playlist | Je modifie `PLAYLISTS` dans `config.env`, puis `bash deploy/deploy.sh` |
| Changer l'heure du lancement | Je modifie `SCHEDULE` dans `config.env`, puis `bash deploy/deploy.sh` |
| Lancer un run maintenant | `gcloud run jobs execute automatic-youtube-downloader --region=europe-west1` |
| Voir les logs | Console → **Cloud Run → Jobs → automatic-youtube-downloader → Exécutions** |
| Mettre à jour yt-dlp (si YouTube casse quelque chose) | `bash deploy/deploy.sh` (l'image est reconstruite avec la dernière version) |

Un morceau qui a déjà été téléchargé ne l'est plus jamais, même si tu le supprimes du Drive. Tu peux donc vider
le dossier Drive au fur et à mesure que tu ranges les morceaux dans ta bibliothèque DJ.

## Dépannage

**« Sign in to confirm you're not a bot » dans les logs**
YouTube bloque parfois les serveurs de Google Cloud. Le run s'arrête proprement et reprendra le lendemain.
Si ça dure, deux solutions :

1. **Cookies YouTube** (gratuit). Utilise de préférence un compte Google secondaire, que YouTube pourrait
   signaler.
   1. Ouvre une fenêtre de navigation privée et connecte-toi à YouTube.
   2. Avec l'extension *Get cookies.txt LOCALLY*, exporte les cookies de youtube.com dans `cookies.txt`, à la
      racine du projet.
   3. Ferme la fenêtre privée, puis relance `bash deploy/deploy.sh`.
2. **Proxy résidentiel** (payant, quelques € par Go, et un morceau fait environ 5 Mo) : renseigne `PROXY_URL`
   dans `config.env`, puis relance `bash deploy/deploy.sh`.

**« Token Google Drive refusé »**
L'app OAuth est sans doute restée en mode « Test » (voir l'étape 3.3). Passe-la en Production, refais l'étape 4,
puis relance `bash deploy/deploy.sh`.

**Un morceau a un mauvais nom**
Le nom vient du titre YouTube. Renomme le fichier à la main dans le Drive, le script ne le retouchera pas.

**Un morceau échoue à chaque fois** (vidéo bloquée dans ton pays, supprimée…)
Le script réessaie 3 jours de suite, puis abandonne ce morceau.

## Organisation du code

```
automatic_youtube_downloader/
  __main__.py   orchestration : lister, filtrer, télécharger, déposer
  youtube.py    lecture des playlists et téléchargement (yt-dlp)
  naming.py     « Artiste - Titre » à partir du titre YouTube
  tagging.py    tags ID3 et pochette
  storage.py    Google Drive, dossier local, fichier d'état
scripts/get_drive_token.py   autorisation Google Drive (une seule fois)
deploy/deploy.sh             déploiement Google Cloud
```

Lancer les tests : `pip install pytest && pytest`
