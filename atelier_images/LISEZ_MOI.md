# Atelier Images

Double-clique sur **Atelier Images.exe** à la racine du dossier portable.
Le lanceur démarre les serveurs en arrière-plan, sans console, puis ouvre ton navigateur par défaut
sur http://127.0.0.1:8189 une fois Atelier et ComfyUI disponibles. Un démarrage lent peut prendre
jusqu'à six minutes ; une boîte de dialogue signale un échec. Les serveurs déjà actifs sont réutilisés.
Plusieurs doubles-clics pendant le démarrage ne lancent pas plusieurs instances du lanceur.

L'exécutable est un lanceur : conserve-le avec `start.ps1`, `atelier_images`, `ComfyUI` et
`python_embeded`. Il ne contient ni les modèles ni Python. Fermer le navigateur ne termine pas
les serveurs, qui restent disponibles pour la prochaine ouverture.

### Recréer l'exécutable

Ouvre PowerShell à la racine du projet, puis exécute :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_launcher.ps1
```

La compilation utilise le compilateur C# du .NET Framework installé avec Windows, sans téléchargement.
Le code source est `atelier_images/launcher/Launcher.cs`. Le résultat est `Atelier Images.exe`,
avec une copie de compilation dans `build/launcher`. Ces fichiers générés sont ignorés par Git.
`ExecutionPolicy Bypass` concerne uniquement ce processus, sans modifier la configuration Windows.
L'exécutable produit n'est pas signé numériquement.

Le lancement par double-clic a été confirmé fonctionnel par l'utilisateur.
Certaines stratégies Windows peuvent néanmoins bloquer un exécutable non signé,
comme cela s'est produit dans le contexte de test automatisé. Dans ce cas, une autorisation
conforme à la stratégie ou une signature acceptée est nécessaire ; recompiler ne suffit pas.

Pour lancer le script manuellement depuis une console PowerShell :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Utilise l'exécutable pour l'ouverture sans fenêtre de console.
Le fichier `Lancer_Atelier_Images.bat` reste disponible comme ancien lanceur avec console.

Les diagnostics du nouveau lanceur sont dans `atelier_images/launcher.log`,
`atelier_images/launcher-server.stdout.log`, `atelier_images/launcher-server.stderr.log`
et `atelier_images/comfyui.log`. Les deux journaux `launcher-server` sont remplacés au prochain
nouveau démarrage du serveur ; `launcher.log` et `comfyui.log` sont alimentés à la suite.


1. Écris une description, en français ou en anglais.
2. Choisis Carré, Portrait ou Paysage.
3. Choisis le nombre d'images par prompt, puis clique sur **Ajouter à la file**. Le premier chargement peut prendre quelques minutes.

Clique sur une image de la galerie pour l'agrandir, la télécharger ou reprendre sa description et sa seed.
Une seed vide produit une nouvelle variation. Avec la même seed, la même description et le même format, tu peux reproduire une composition.
Avec FLUX ou Stable Diffusion, chaque description crée de nouvelles images. Avec Qwen, tu peux aussi ajouter une image à retoucher.

## Stable Diffusion et profil 8 Go

Choisis **Stable Diffusion 1.5 · léger · 8 Go** dans **Mon modèle**. Il utilise 20 étapes,
une seule image à la fois et un décodage par tuiles pour réduire la mémoire nécessaire.
Le modèle est dans `ComfyUI/models/checkpoints/v1-5-pruned-emaonly.safetensors`.
Sur une nouvelle installation, télécharge-le avec :

```powershell
.\python_embeded\python.exe -s setup_sd_local.py
```

Le lanceur active le mode mémoire réduite, réserve 1 Go pour Windows et désactive le cache
des résultats intermédiaires de ComfyUI. Une mention sous les jauges indique si ce profil est actif.
Si tu avais lancé ComfyUI séparément, termine ses générations, ferme son processus, puis relance Atelier.
Les formats restent limités à 512 × 512, 512 × 768 ou 768 × 512.

Les jauges VRAM et RAM montrent l'utilisation globale de la machine toutes les deux secondes,
y compris celle des autres applications. Elles passent en couleur d'alerte à forte occupation.
Ce profil vise une carte de 8 Go ; il ne limite pas la mémoire consommée par d'autres logiciels.

## File de prompts et séries d'images

- **Images par prompt** : de 1 à 50, calculées une par une.
- **Plusieurs prompts : un par ligne** : chaque ligne devient un prompt distinct avec le nombre choisi.
- Tu peux ajouter des prompts pendant une génération et changer de modèle pour les suivants.
- **Mettre en pause** laisse finir l'image en cours, puis attend **Reprendre**.
- **Annuler** supprime les images restantes du prompt ; une image déjà en calcul se termine.
- Les tâches réussies et annulées disparaissent automatiquement de la liste, sans supprimer les PNG.
- Les erreurs restent visibles ; **Retirer** permet de fermer une entrée en erreur.

Exemple : trois lignes et quatre images par prompt donnent douze images dans la file.
La limite est de 200 images restantes. Chaque image utilise la seed initiale + son numéro dans la série.
Les paramètres et la référence de retouche sont figés au moment de l'ajout.

La file reste active si tu fermes l'onglet. Elle est enregistrée dans `atelier_images/queue_state.json`
(prompts inclus, fichier exclu de Git). Au redémarrage d'Atelier, les travaux sont retrouvés si ComfyUI
dispose encore de leur historique. Un résultat incertain n'est jamais renvoyé automatiquement :
une erreur invite à vérifier la galerie pour éviter les doublons. Une erreur mémoire met la file en pause.

## Prompts longs

Le champ n'est plus limité à 6 000 caractères au total. Il accepte jusqu'à **100 000 caractères
par prompt** et **1 000 000 de caractères par envoi**. En mode multi-prompts, chaque ligne est
un prompt distinct. Un compteur indique la longueur totale et celle de la ligne la plus longue.
Les dépassements sont signalés, jamais tronqués silencieusement par Atelier. La capacité de
compréhension du modèle reste distincte de cette limite de saisie.

## Supprimer une image

Le bouton **Supprimer** sous chaque image demande une confirmation, puis efface le PNG sans passer
par la corbeille, y compris son prompt et son workflow intégrés. Le nettoyage cible aussi les
références dans la file, les anciens états d'Atelier, l'historique du moteur ComfyUI local,
le catalogue SQLite et les mentions correspondantes dans les journaux du projet.

Les autres images sont conservées, même si elles partagent exactement le même prompt.
Le prompt partagé reste donc dans leurs PNG et dans leurs propres enregistrements.
Une série encore active doit se terminer ou être annulée avant de supprimer une de ses images.
ComfyUI doit être joignable pour nettoyer son historique. Les échecs de nettoyage sont affichés :
une image effacée ne signifie pas forcément que toutes les étapes annexes ont réussi.

Cette fonction couvre les emplacements gérés par Atelier. Elle ne peut pas supprimer des copies
téléchargées ailleurs, des images de référence importées séparément, captures d'écran, profils de
navigateur, sauvegardes, fichiers synchronisés ou éléments déjà partagés avec un service externe.
Elle ne constitue pas un effacement physique garanti du SSD. Aucun historique distant de
génération n'est utilisé par notre pipeline local. Un historique ComfyUI partagé avec d'autres
sorties ou une prévisualisation liée non prise en charge est conservé et signalé comme nettoyage incomplet.

Les PNG restent dans `ComfyUI/output` et contiennent le workflow ComfyUI. La galerie affiche les 150 dernières images de cet atelier et du test initial.
## Changer de modèle

Le menu **Mon modèle** permet de choisir un modèle installé. Ton choix reste mémorisé dans ce navigateur.
L'import de modèles dans l'interface a été retiré. Pour ajouter un modèle, demande son installation et sa configuration dans cette conversation.

FLUX Schnell conserve ses 4 étapes et ses encodeurs CLIP-L/T5. Le profil Dev utilise 20 étapes et une guidance de 3,5.

## Qwen Lightning (4 étapes) et fiches @Nom

**Qwen 2.1 Lightning · 4 étapes** (premier choix de **Mon modèle**) = les poids Qwen 2.1 déjà installés + le LoRA
LightX2V Lightning v2-RL (`ComfyUI/models/loras/qwen21_lightning_v2_rl_4steps_rank64.safetensors`, SHA-256
`02363ec9…3b09c6d`), avec le calendrier de 4 sigmas publié par ses auteurs. Il garde la compréhension fine de Qwen
pour une fraction du temps. Les mesures avant / après sont dans `BENCHMARK_LIGHTNING.md` (`bench.py` les refait).

**Fiches** : `atelier_images/characters/characters.json` (exemple : `characters.example.json`, dossier ignoré par Git).
Écris `@Nom` dans une idée : la description exacte de la fiche est insérée à chaque fois. Si la fiche a une image
(📷), Qwen la reçoit comme référence et garde le même personnage (jusqu'à 4 fiches avec image par prompt).
Dans une image de la galerie, **Image de la fiche** l'enregistre comme référence de la fiche choisie.
Avec FLUX ou Stable Diffusion, seule la description est insérée.

## Qwen Image 2.1 : génération et retouche

Sélectionne **Qwen Image 2.1 Uncensored · génération et retouche** dans **Mon modèle**.
Sans image de référence, décris l'image souhaitée, choisis le format et lance la génération.
Pour retoucher, ajoute une image PNG, JPEG ou WebP dans **Retoucher une image avec Qwen**, puis écris par exemple « Remplace le fond par un jardin ensoleillé ».
Clique sur **Retirer** pour revenir à la création à partir du texte seul.

La retouche accepte une référence à la fois (20 Mo et 25 mégapixels maximum). Une copie normalisée est conservée dans `ComfyUI/input` ; le fichier original est préservé.
Elle conserve les proportions de la référence, avec une surface proche de 512 × 512 pixels. Le sélecteur de format sert à la génération sans référence.
Qwen utilise 28 étapes. Son encodeur Qwen3-VL s’exécute sur GPU avec déchargement partiel en RAM : il ne tient pas entièrement dans 8 Go de VRAM. Le cache Qwen reste sur CPU. Le premier chargement et la taille de l’image influencent le temps de génération.

Source choisie : https://huggingface.co/spaces/fishpasters/uncensored-imageTOimage2Ref
Poids locaux quantifiés : https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-GGUF
Modèle Q4_K_M, encodeur INT8 ConvRot et VAE Qwen 2.1. Il s'agit de la version locale quantifiée fournie par l'auteur ; le Space utilise Diffusers avec le modèle BF16 et son LoRA.
Le script `setup_qwen_local.py` permet de reprendre les téléchargements et de vérifier leurs sommes SHA-256.
Le chargeur GGUF a reçu l'identifiant d'architecture `qwen_image21`, déjà géré par le cœur ComfyUI installé ; sa version précédente est sauvegardée dans `atelier_images/gguf_loader_before_qwen.py.bak`.
Le petit nœud `AtelierLoadReference` charge les PNG de référence avec Pillow pour respecter le contournement PyAV de cette installation. Aucune dépendance vidéo n'est nécessaire.

Le nom du modèle et le workflow sont enregistrés dans chaque PNG. **Reprendre cette idée** reprend aussi la référence de retouche si elle existe encore.

Tout fonctionne localement. Aucun compte, service distant ou téléchargement de modèle supplémentaire.
En cas d'erreur de démarrage, consulte `atelier_images/comfyui.log`. Fermer l'atelier ne ferme pas ComfyUI s'il tourne en arrière-plan.


### Tout supprimer

Dans ? Mes cr?ations ?, le bouton ? Tout supprimer ? demande une confirmation avant de supprimer sans corbeille tous les fichiers des dossiers ComfyUI/output, input, temp, previews et user/default/workflows, y compris ceux cr??s directement dans ComfyUI. Il vide les prompts de la file, la met en pause et nettoie l?historique ComfyUI, le catalogue des images et les journaux locaux. Mets la file en pause et attends la fin de la g?n?ration en cours avant de l?utiliser. ComfyUI doit ?tre disponible.

Le code, les mod?les et les workflows techniques de l?application sont conserv?s. Les journaux techniques peuvent se recr?er. Les fichiers t?l?charg?s ailleurs, sauvegardes, captures, autres onglets et caches du navigateur sont exclus. Ce nettoyage ne garantit pas un effacement physique du SSD. Tout ?chec partiel est signal? ; tu peux r?essayer.
